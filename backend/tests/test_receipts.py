import copy
import unittest
from unittest.mock import patch

from engine.models import (
    OptimizationPolicy,
    Scenario,
)
from engine.optimizer import optimize_interventions
from engine.receipt_fixtures import signature_receipt_fixture
from engine.receipts import (
    DecisionReceipt,
    ReceiptPayload,
    create_decision_receipt,
    export_receipt_json,
    payload_sha256,
)
from engine.scenarios import (
    coupled_utility_scenario,
    fairness_tradeoff_scenario,
    hand_calculated_scenario,
    signature_scenario,
)
from engine.simulation import simulate
from engine.verification import VerificationStatus, verify_decision_receipt


def _receipt(
    scenario: Scenario | None = None,
    policy: OptimizationPolicy | None = None,
) -> DecisionReceipt:
    scenario = scenario or signature_scenario()
    result = optimize_interventions(scenario, policy)
    return create_decision_receipt(
        scenario,
        result,
        include_execution_metadata=False,
    )


def _rehash(receipt: DecisionReceipt) -> dict:
    exported = copy.deepcopy(receipt.model_dump(mode="json"))
    payload = ReceiptPayload.model_validate(exported["payload"])
    exported["integrity"]["digest"] = payload_sha256(payload)
    return exported


class DecisionReceiptTests(unittest.TestCase):
    def test_receipt_fixture_exports_deterministically(self) -> None:
        first = signature_receipt_fixture()
        second = signature_receipt_fixture()

        self.assertEqual(export_receipt_json(first), export_receipt_json(second))
        self.assertEqual(
            payload_sha256(first.payload),
            payload_sha256(second.payload),
        )
        self.assertEqual(len(first.integrity.digest), 64)
        self.assertIsNone(first.execution_metadata)

    def test_execution_timing_is_outside_the_canonical_digest(self) -> None:
        receipt = _receipt()
        data = receipt.model_dump(mode="json")
        data["execution_metadata"] = {"exact_search_duration_ns": 123}
        timed = DecisionReceipt.model_validate(data)
        report = verify_decision_receipt(timed)

        self.assertEqual(timed.integrity.digest, receipt.integrity.digest)
        self.assertTrue(report.valid, report.issues)

    def test_signature_receipt_reconstructs_and_verifies(self) -> None:
        scenario = signature_scenario()
        receipt = _receipt(scenario)
        reconstructed = Scenario.model_validate(receipt.payload.scenario)
        report = verify_decision_receipt(export_receipt_json(receipt))

        self.assertEqual(reconstructed, scenario)
        self.assertTrue(report.valid, report.issues)
        self.assertTrue(
            all(
                getattr(report, field) == VerificationStatus.PASSED
                for field in (
                    "schema_status",
                    "version_status",
                    "integrity_status",
                    "input_status",
                    "replay_status",
                    "baseline_status",
                    "optimality_status",
                )
            )
        )

    def test_verifier_does_not_call_production_optimizer(self) -> None:
        receipt = _receipt()
        with patch(
            "engine.optimizer.optimize_interventions",
            side_effect=AssertionError("optimizer must not be used by verifier"),
        ):
            report = verify_decision_receipt(receipt)
        self.assertTrue(report.valid, report.issues)

    def test_hand_calculated_fixture_checks_trace_metrics_and_replay(self) -> None:
        receipt = _receipt(hand_calculated_scenario())
        report = verify_decision_receipt(receipt)
        metric = receipt.payload.recommended_plan.demand_metrics[0]
        scrubber_states = [
            next(asset for asset in step.assets if asset.asset_id == "scrubber")
            .service_available
            for step in receipt.payload.selected_trace
        ]
        pump_reserve = [
            next(asset for asset in step.assets if asset.asset_id == "pump").buffer_units
            for step in receipt.payload.selected_trace
        ]

        self.assertTrue(report.valid, report.issues)
        self.assertEqual(metric.served_minutes, 2)
        self.assertEqual(metric.service_person_minutes, 20)
        self.assertEqual(metric.coverage_parts_per_million, 500_000)
        self.assertEqual(metric.weighted_service_person_minutes, 40)
        self.assertEqual(scrubber_states, [False, False, True, True, True])
        self.assertEqual(pump_reserve, [1, 0, 1, 2, 2])

    def test_payload_change_without_new_digest_fails_integrity(self) -> None:
        data = _rehash(_receipt())
        data["payload"]["scenario"]["assets"][0]["name"] = "Altered feeder label"
        report = verify_decision_receipt(data)

        self.assertEqual(report.integrity_status, VerificationStatus.FAILED)
        self.assertEqual(report.input_status, VerificationStatus.PASSED)
        self.assertFalse(report.valid)

    def test_changed_input_with_new_digest_still_fails_replay_and_optimality(self) -> None:
        data = _rehash(_receipt())
        data["payload"]["scenario"]["demands"][0]["population"] += 1
        data = _rehash(DecisionReceipt.model_validate(data))
        report = verify_decision_receipt(data)

        self.assertEqual(report.integrity_status, VerificationStatus.PASSED)
        self.assertEqual(report.input_status, VerificationStatus.PASSED)
        self.assertEqual(report.replay_status, VerificationStatus.FAILED)
        self.assertEqual(report.optimality_status, VerificationStatus.FAILED)

    def test_rehashed_false_objective_is_rejected_by_replay(self) -> None:
        data = _rehash(_receipt())
        data["payload"]["recommended_plan"]["objective"][
            "weighted_service_person_minutes"
        ] += 1
        report = verify_decision_receipt(_rehash(DecisionReceipt.model_validate(data)))

        self.assertEqual(report.integrity_status, VerificationStatus.PASSED)
        self.assertEqual(report.replay_status, VerificationStatus.FAILED)
        self.assertEqual(report.optimality_status, VerificationStatus.PASSED)

    def test_impossible_resource_assignment_is_rejected(self) -> None:
        data = _rehash(_receipt())
        data["payload"]["recommended_plan"]["interventions"][0][
            "resource_id"
        ] = "unknown-resource"
        report = verify_decision_receipt(_rehash(DecisionReceipt.model_validate(data)))

        self.assertEqual(report.input_status, VerificationStatus.FAILED)
        self.assertEqual(report.replay_status, VerificationStatus.FAILED)
        self.assertIn(
            "invalid_recommended_assignment",
            {issue.code for issue in report.issues},
        )

    def test_rehashed_baseline_tampering_is_rejected(self) -> None:
        data = _rehash(_receipt())
        data["payload"]["baseline_comparisons"][0]["plan"]["objective"][
            "weighted_service_person_minutes"
        ] += 1
        report = verify_decision_receipt(_rehash(DecisionReceipt.model_validate(data)))

        self.assertEqual(report.integrity_status, VerificationStatus.PASSED)
        self.assertEqual(report.baseline_status, VerificationStatus.FAILED)

    def test_rehashed_fairness_metric_tampering_is_rejected(self) -> None:
        data = _rehash(_receipt())
        data["payload"]["recommended_plan"]["community_service_coverages"][0][
            "coverage_parts_per_million"
        ] += 1
        report = verify_decision_receipt(_rehash(DecisionReceipt.model_validate(data)))

        self.assertEqual(report.integrity_status, VerificationStatus.PASSED)
        self.assertEqual(report.replay_status, VerificationStatus.FAILED)
        self.assertIn(
            "selected_outcome_mismatch",
            {issue.code for issue in report.issues},
        )

    def test_rehashed_candidate_count_falsification_is_rejected(self) -> None:
        data = _rehash(_receipt())
        data["payload"]["search"]["candidate_plans"] += 1
        report = verify_decision_receipt(_rehash(DecisionReceipt.model_validate(data)))

        self.assertEqual(report.integrity_status, VerificationStatus.PASSED)
        self.assertEqual(report.optimality_status, VerificationStatus.FAILED)

    def test_rehashed_inferior_plan_cannot_claim_optimality(self) -> None:
        receipt = _receipt()
        data = _rehash(receipt)
        static_plan = data["payload"]["baseline_comparisons"][1]["plan"]
        data["payload"]["recommended_plan"] = static_plan
        scenario = Scenario.model_validate(data["payload"]["scenario"])
        replay_scenario = Scenario.model_validate(
            {
                **scenario.model_dump(),
                "interventions": static_plan["interventions"],
            }
        )
        data["payload"]["selected_trace"] = [
            step.model_dump(mode="json")
            for step in simulate(replay_scenario).steps
        ]
        data["payload"]["search"]["selected_primary_score"] = (
            static_plan["objective"]["weighted_service_person_minutes"]
        )
        data["payload"]["search"]["selected_primary_score_loss"] = 160
        data["payload"]["search"]["fairness_tradeoff_applied"] = False
        report = verify_decision_receipt(_rehash(DecisionReceipt.model_validate(data)))

        self.assertEqual(report.integrity_status, VerificationStatus.PASSED)
        self.assertEqual(report.replay_status, VerificationStatus.PASSED)
        self.assertEqual(report.optimality_status, VerificationStatus.FAILED)

    def test_unsupported_versions_are_reported(self) -> None:
        for field in (
            "schema_version",
            "canonicalization_version",
            "simulation_model_version",
            "optimizer_version",
        ):
            with self.subTest(field=field):
                data = _rehash(_receipt())
                data["payload"][field] = "999.0"
                report = verify_decision_receipt(
                    _rehash(DecisionReceipt.model_validate(data))
                )

                self.assertEqual(report.version_status, VerificationStatus.FAILED)
                self.assertFalse(report.valid)
                if field in ("simulation_model_version", "optimizer_version"):
                    self.assertEqual(
                        report.optimality_status,
                        VerificationStatus.NOT_CHECKED,
                    )

    def test_missing_and_incomplete_scenario_inputs_are_reported(self) -> None:
        missing = _rehash(_receipt())
        del missing["payload"]["scenario"]
        missing_report = verify_decision_receipt(missing)
        incomplete = _rehash(_receipt())
        incomplete["payload"]["scenario"] = {"id": "missing-fields"}
        incomplete_report = verify_decision_receipt(
            _rehash(DecisionReceipt.model_validate(incomplete))
        )

        self.assertEqual(missing_report.schema_status, VerificationStatus.FAILED)
        self.assertEqual(missing_report.input_status, VerificationStatus.FAILED)
        self.assertIn(
            "missing_required_replay_input",
            {issue.code for issue in missing_report.issues},
        )
        self.assertEqual(incomplete_report.input_status, VerificationStatus.FAILED)
        self.assertIn(
            "invalid_scenario_inputs",
            {issue.code for issue in incomplete_report.issues},
        )

    def test_malformed_and_duplicate_key_json_is_rejected(self) -> None:
        malformed = verify_decision_receipt("{")
        duplicate_key = verify_decision_receipt('{"payload": {}, "payload": {}}')
        self.assertEqual(malformed.schema_status, VerificationStatus.FAILED)
        self.assertEqual(duplicate_key.schema_status, VerificationStatus.FAILED)

    def test_fairness_receipt_replays_explicit_score_tradeoff(self) -> None:
        receipt = _receipt(
            fairness_tradeoff_scenario(),
            OptimizationPolicy(primary_tolerance_ppm=400_000),
        )
        report = verify_decision_receipt(receipt)

        self.assertTrue(report.valid, report.issues)
        self.assertEqual(receipt.payload.search.best_primary_score, 200)
        self.assertEqual(receipt.payload.search.selected_primary_score, 120)
        self.assertEqual(receipt.payload.search.selected_primary_score_loss, 80)
        self.assertTrue(receipt.payload.search.fairness_tradeoff_applied)
        self.assertEqual(
            receipt.payload.recommended_plan.objective.minimum_community_service_coverage_ppm,
            500_000,
        )

    def test_coupled_utility_scenario_shows_exact_gain_over_baselines(self) -> None:
        scenario = coupled_utility_scenario()
        result = optimize_interventions(scenario)
        receipt = create_decision_receipt(
            scenario,
            result,
            include_execution_metadata=False,
        )
        report = verify_decision_receipt(receipt)
        baseline_scores = {
            comparison.baseline.value: (
                comparison.plan.objective.weighted_service_person_minutes
            )
            for comparison in result.baseline_comparisons
        }

        self.assertTrue(report.valid, report.issues)
        self.assertEqual(result.candidate_plans, 8)
        self.assertEqual(result.feasible_plans, 8)
        self.assertEqual(result.plans_evaluated, 8)
        self.assertEqual(
            {
                intervention.dependency_group_id
                for intervention in result.selected_plan.interventions
            },
            {"pump-power", "pump-source-water"},
        )
        self.assertEqual(result.selected_plan.objective.weighted_service_person_minutes, 1_100)
        self.assertEqual(
            baseline_scores,
            {"no_intervention": 0, "static_priority": 720, "greedy": 720},
        )
        comparisons = {
            comparison.baseline.value: comparison
            for comparison in result.baseline_comparisons
        }
        self.assertEqual(
            [
                (action.resource_id, action.target_asset_id, action.dependency_group_id)
                for action in comparisons["static_priority"].plan.interventions
            ],
            [("water-tanker", "air-scrubber", "scrubber-water")],
        )
        self.assertEqual(
            [
                (action.resource_id, action.target_asset_id, action.dependency_group_id)
                for action in comparisons["greedy"].plan.interventions
            ],
            [("water-tanker", "air-scrubber", "scrubber-water")],
        )


if __name__ == "__main__":
    unittest.main()
