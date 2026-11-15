import unittest

from engine.api import SCENARIOS
from engine.certificates import (
    build_coordination_certificate,
    verify_coordination_certificate,
    _body_digest,
)
from engine.optimizer import optimize_interventions
from engine.scenarios import coupled_utility_scenario, signature_scenario

GEN = 'assignment:["mobile-generator","pump","pump-power"]'
TANKER = 'assignment:["water-tanker","pump","pump-source-water"]'
TANKER_SCRUBBER = 'assignment:["water-tanker","air-scrubber","scrubber-water"]'


def _certificate(scenario):
    result = optimize_interventions(scenario)
    return build_coordination_certificate(scenario, result.selected_plan.interventions), result


class CoupledScenarioTests(unittest.TestCase):
    def setUp(self):
        self.scenario = coupled_utility_scenario()
        self.cert, self.result = _certificate(self.scenario)

    def test_each_action_alone_is_worthless_together_they_are_1100(self):
        scores = {item.intervention_ids: item.weighted_service_person_minutes for item in self.cert.subset_scores}
        self.assertEqual(scores[()], 0)
        self.assertEqual(scores[(GEN,)], 0)
        self.assertEqual(scores[(TANKER,)], 0)
        self.assertEqual(scores[tuple(sorted((GEN, TANKER)))], 1100)

    def test_joint_gain_is_the_whole_value(self):
        self.assertEqual(self.cert.kind, "complementary")
        self.assertEqual(self.cert.joint_gain, 1100)
        self.assertEqual(self.cert.joint_gain_share_ppm, 1_000_000)

    def test_both_actions_are_necessary(self):
        self.assertTrue(all(row.necessary for row in self.cert.necessity))
        self.assertEqual({row.loss_without for row in self.cert.necessity}, {1100})

    def test_full_recovery_needs_exactly_the_pair(self):
        self.assertEqual(self.cert.full_recovery_minimal_sets, (tuple(sorted((GEN, TANKER))),))

    def test_greedy_is_trapped_at_720(self):
        greedy = self.cert.greedy
        self.assertTrue(greedy.trap_detected)
        self.assertEqual(greedy.final_score, 720)
        self.assertEqual(greedy.shortfall_versus_plan, 380)
        self.assertEqual(greedy.steps[0].intervention_id, TANKER_SCRUBBER)
        self.assertEqual(len(greedy.steps), 1)

    def test_greedy_witness_matches_the_production_greedy_baseline(self):
        production = {b.baseline.value: b for b in self.result.baseline_comparisons}["greedy"]
        self.assertEqual(
            production.plan.objective.weighted_service_person_minutes,
            self.cert.greedy.final_score,
        )

    def test_certificate_verifies(self):
        report = verify_coordination_certificate(self.scenario, self.cert)
        self.assertEqual(report.status, "passed", report.checks)

    def test_certificate_round_trips_through_json(self):
        report = verify_coordination_certificate(self.scenario, self.cert.model_dump(mode="json"))
        self.assertEqual(report.status, "passed")

    def test_build_is_deterministic(self):
        again, _ = _certificate(coupled_utility_scenario())
        self.assertEqual(again.certificate_sha256, self.cert.certificate_sha256)


class TamperAndStaleTests(unittest.TestCase):
    def setUp(self):
        self.scenario = coupled_utility_scenario()
        self.cert, _ = _certificate(self.scenario)

    def _failed_checks(self, report):
        return {check.name for check in report.checks if not check.passed}

    def test_edited_field_without_rehash_fails_integrity(self):
        data = self.cert.model_dump(mode="json")
        data["joint_gain"] = 5000
        report = verify_coordination_certificate(self.scenario, data)
        self.assertEqual(report.status, "failed")
        self.assertIn("payload_integrity", self._failed_checks(report))

    def test_rehashed_forgery_is_caught_by_replay(self):
        data = self.cert.model_dump(mode="json")
        data["subset_scores"][1]["weighted_service_person_minutes"] = 999
        forged = type(self.cert).model_validate(data)
        forged = forged.model_copy(update={"certificate_sha256": _body_digest(forged)})
        report = verify_coordination_certificate(self.scenario, forged)
        self.assertEqual(report.status, "failed")
        self.assertIn("subset_replay", self._failed_checks(report))
        self.assertNotIn("payload_integrity", self._failed_checks(report))

    def test_forged_greedy_witness_is_caught(self):
        data = self.cert.model_dump(mode="json")
        data["greedy"]["trap_detected"] = False
        forged = type(self.cert).model_validate(data)
        forged = forged.model_copy(update={"certificate_sha256": _body_digest(forged)})
        report = verify_coordination_certificate(self.scenario, forged)
        self.assertIn("greedy_witness", self._failed_checks(report))

    def test_edited_scenario_makes_certificate_stale(self):
        data = self.scenario.model_dump(mode="python")
        for resource in data["resources"]:
            for route in resource["travel_times"]:
                if resource["id"] == "water-tanker" and route["asset_id"] == "pump":
                    route["travel_minutes"] = 5
        edited = type(self.scenario).model_validate(data)
        report = verify_coordination_certificate(edited, self.cert)
        self.assertEqual(report.status, "failed")
        self.assertIn("scenario_binding", self._failed_checks(report))

    def test_garbage_input_fails_closed(self):
        report = verify_coordination_certificate(self.scenario, {"version": "nope"})
        self.assertEqual(report.status, "failed")


class CounterexampleTests(unittest.TestCase):
    def test_single_action_plan_reports_no_coordination(self):
        scenario = signature_scenario()
        cert, _ = _certificate(scenario)
        self.assertEqual(cert.kind, "single_action")
        self.assertEqual(cert.joint_gain, 0)
        self.assertEqual(cert.joint_gain_share_ppm, 0)
        self.assertEqual(len(cert.actions), 1)
        self.assertTrue(cert.necessity[0].necessary)
        self.assertEqual(verify_coordination_certificate(scenario, cert).status, "passed")

    def test_rejects_non_optimizer_actions(self):
        scenario = coupled_utility_scenario()
        _, result = _certificate(scenario)
        bad = result.selected_plan.interventions[0].model_copy(update={"dispatch_minute": 2})
        with self.assertRaises(ValueError):
            build_coordination_certificate(scenario, (bad,))


class AllBuiltInScenariosTests(unittest.TestCase):
    def test_every_scenario_certifies_and_matches_production_greedy(self):
        for key, (_, _, factory) in SCENARIOS.items():
            with self.subTest(scenario=key):
                scenario = factory()
                cert, result = _certificate(scenario)
                report = verify_coordination_certificate(scenario, cert)
                self.assertEqual(report.status, "passed", report.checks)
                greedy = {b.baseline.value: b for b in result.baseline_comparisons}["greedy"]
                self.assertEqual(
                    greedy.plan.objective.weighted_service_person_minutes,
                    cert.greedy.final_score,
                )
                self.assertEqual(cert.plan_score, result.selected_plan.objective.weighted_service_person_minutes)


class ProvenanceTests(unittest.TestCase):
    """The certificate's numbers must come from simulator replays and nothing else."""

    def test_every_subset_score_equals_a_recorded_simulator_run(self):
        import engine.certificates as module

        scenario = coupled_utility_scenario()
        result = optimize_interventions(scenario)
        real = module.simulate
        calls = []

        def spy(candidate):
            out = real(candidate)
            calls.append(
                (tuple(sorted(i.id for i in candidate.interventions)), out.total_weighted_service_person_minutes)
            )
            return out

        module.simulate = spy
        try:
            cert = build_coordination_certificate(scenario, result.selected_plan.interventions)
        finally:
            module.simulate = real
        for subset in cert.subset_scores:
            self.assertIn(
                (subset.intervention_ids, subset.weighted_service_person_minutes), calls
            )

    def test_inflating_the_simulator_changes_the_certificate(self):
        import engine.certificates as module

        scenario = coupled_utility_scenario()
        result = optimize_interventions(scenario)
        honest = build_coordination_certificate(scenario, result.selected_plan.interventions)
        real = module.simulate

        def inflated(candidate):
            out = real(candidate)
            return out.model_copy(
                update={
                    "total_weighted_service_person_minutes": out.total_weighted_service_person_minutes
                    + (7 if candidate.interventions else 0)
                }
            )

        module.simulate = inflated
        try:
            skewed = build_coordination_certificate(scenario, result.selected_plan.interventions)
        finally:
            module.simulate = real
        self.assertNotEqual(honest.certificate_sha256, skewed.certificate_sha256)

    def test_verification_never_calls_the_optimizer(self):
        import engine.optimizer as optimizer

        scenario = coupled_utility_scenario()
        cert, _ = _certificate(scenario)
        real = optimizer.optimize_interventions

        def forbidden(*args, **kwargs):
            raise AssertionError("verifier must not call the optimizer")

        optimizer.optimize_interventions = forbidden
        try:
            report = verify_coordination_certificate(scenario, cert)
        finally:
            optimizer.optimize_interventions = real
        self.assertEqual(report.status, "passed")


class ReceiptCompatibilityTests(unittest.TestCase):
    def test_existing_receipt_still_verifies_and_is_unchanged_by_certificates(self):
        from engine.api import evaluate_scenario
        from engine.verification import verify_decision_receipt

        response = evaluate_scenario(coupled_utility_scenario())
        self.assertIn("coordination_certificate", response)
        report = verify_decision_receipt(response["receipt"])
        self.assertTrue(report.valid, report.issues)
        self.assertNotIn("coordination_certificate", json_dump(response["receipt"]))


def json_dump(value):
    import json

    return json.dumps(value)

class CertificateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scenario = coupled_utility_scenario()
        self.cert, _ = _certificate(self.scenario)

    def rehash(self, data):
        cert = type(self.cert).model_validate(data)
        return cert.model_copy(update={"certificate_sha256": _body_digest(cert)})

    def test_rehashed_action_metadata_share_and_scope_are_checked(self):
        for field in ("resource_id", "target_asset_id", "dependency_group_id"):
            with self.subTest(field=field):
                data = self.cert.model_dump(mode="json")
                data["actions"][0][field] = "invented-reference"
                self.assertEqual(verify_coordination_certificate(self.scenario, self.rehash(data)).status, "failed")
        for field, value in (("joint_gain_share_ppm", 123), ("limitations", {"statements": []})):
            with self.subTest(field=field):
                data = self.cert.model_dump(mode="json")
                data[field] = value
                self.assertEqual(verify_coordination_certificate(self.scenario, self.rehash(data)).status, "failed")

    def test_rehashed_timeline_is_checked(self):
        data = self.cert.model_dump(mode="json")
        data["subset_scores"][0]["availability"][0]["service_available"][0] = True
        self.assertEqual(verify_coordination_certificate(self.scenario, self.rehash(data)).status, "failed")

    def test_schema_does_not_coerce_claims_and_revalidates_model_instances(self):
        for value in ("1100", 1100.0, True):
            forged = self.cert.model_copy(update={"plan_score": value})
            self.assertEqual(verify_coordination_certificate(self.scenario, forged).status, "failed")

    def test_builder_rejects_mislabeled_assignment_and_excess_actions(self):
        scenario = signature_scenario()
        result = optimize_interventions(scenario)
        action = result.selected_plan.interventions[0]
        mislabeled = action.model_copy(update={"id": 'assignment:["mobile-generator","clinic","clinic-power"]'})
        with self.assertRaises(ValueError):
            build_coordination_certificate(scenario, (mislabeled,))
        with self.assertRaisesRegex(ValueError, "at most four"):
            build_coordination_certificate(self.scenario, (action,) * 5)
        data = self.cert.model_dump(mode="json")
        data["actions"] *= 3
        self.assertEqual(verify_coordination_certificate(self.scenario, self.rehash(data)).status, "failed")

    def test_timeline_matches_the_model_and_terminal_boundary_is_retained(self):
        full = next(row for row in self.cert.subset_scores if len(row.intervention_ids) == 2)
        for asset in ("air-scrubber", "water-distribution", "pump"):
            series = next(row for row in full.availability if row.asset_id == asset)
            self.assertEqual(series.service_available, (False, True, True, True, True, True, False))
        # Zero served-minute demands are already matched by the empty subset;
        # matching a recommendation does not assert full-horizon recovery.
        self.assertEqual(self.cert.demand_sufficiency[0].required_served_minutes, 5)

    def test_three_way_classification_does_not_mislabel_pairwise_synergy_as_additive(self):
        from engine.certificates import _kind
        self.assertEqual(_kind(3, 0), "higher_order")
        self.assertEqual(_kind(3, -20), "higher_order")


if __name__ == "__main__":
    unittest.main()
