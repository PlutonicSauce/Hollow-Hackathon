"""Independent replay, metric, baseline, and bounded optimality verification."""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter_ns
from typing import Any, Mapping

from pydantic import ValidationError

from .models import (
    BaselineComparison,
    CommunityServiceCoverage,
    Contract,
    DemandMetric,
    Intervention,
    NonEmptyString,
    OptimizationPolicy,
    NonNegativeInt,
    ObjectiveValue,
    PlanSummary,
    PolicyName,
    Scenario,
    SimulationResult,
)
from .receipts import (
    CANONICALIZATION_VERSION,
    MODEL_ASSUMPTIONS,
    MODEL_LIMITATIONS,
    OPTIMIZER_VERSION,
    RECEIPT_SCHEMA_VERSION,
    RESOURCE_CONSTRAINTS,
    SIMULATION_MODEL_VERSION,
    DecisionReceipt,
    METRIC_DEFINITIONS,
    ReceiptPayload,
    ReceiptSearchSummary,
    canonical_payload_bytes,
)
from .simulation import simulate

_PPM = 1_000_000
_EXPECTED_BASELINES = (
    PolicyName.NO_INTERVENTION,
    PolicyName.STATIC_PRIORITY,
    PolicyName.GREEDY,
)


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_CHECKED = "not_checked"


class VerificationCategory(StrEnum):
    SCHEMA = "schema"
    VERSION = "version"
    INTEGRITY = "integrity"
    INPUT = "input"
    REPLAY = "replay"
    BASELINE = "baseline"
    OPTIMALITY = "optimality"


class VerificationIssue(Contract):
    code: NonEmptyString
    category: VerificationCategory
    message: NonEmptyString


class VerificationReport(Contract):
    valid: bool
    schema_status: VerificationStatus
    version_status: VerificationStatus
    integrity_status: VerificationStatus
    input_status: VerificationStatus
    replay_status: VerificationStatus
    baseline_status: VerificationStatus
    optimality_status: VerificationStatus
    verified_payload_sha256: str | None = None
    verification_duration_ns: NonNegativeInt
    issues: tuple[VerificationIssue, ...]


@dataclass(frozen=True)
class _Candidate:
    resource_id: str
    target_asset_id: str
    dependency_group_id: str
    travel_minutes: int
    setup_minutes: int
    direct_priority: int

    @property
    def deployment_minutes(self) -> int:
        return self.travel_minutes + self.setup_minutes

    def as_intervention(self) -> Intervention:
        action_key = json.dumps(
            [self.resource_id, self.target_asset_id, self.dependency_group_id],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return Intervention(
            id=f"assignment:{action_key}",
            resource_id=self.resource_id,
            target_asset_id=self.target_asset_id,
            dependency_group_id=self.dependency_group_id,
            dispatch_minute=0,
        )


def verify_decision_receipt(
    receipt: DecisionReceipt | str | bytes | Mapping[str, Any],
) -> VerificationReport:
    """Verify a receipt without calling the production optimizer."""
    started_ns = perf_counter_ns()
    issues: list[VerificationIssue] = []
    statuses = {
        "schema_status": VerificationStatus.NOT_CHECKED,
        "version_status": VerificationStatus.NOT_CHECKED,
        "integrity_status": VerificationStatus.NOT_CHECKED,
        "input_status": VerificationStatus.NOT_CHECKED,
        "replay_status": VerificationStatus.NOT_CHECKED,
        "baseline_status": VerificationStatus.NOT_CHECKED,
        "optimality_status": VerificationStatus.NOT_CHECKED,
    }

    try:
        parsed = _parse_receipt(receipt)
    except (ValidationError, TypeError, ValueError) as error:
        statuses["schema_status"] = VerificationStatus.FAILED
        if isinstance(error, ValidationError):
            issues.extend(_validation_issues(error, VerificationCategory.SCHEMA))
            if any(
                item["type"] == "missing"
                and item["loc"][:2] == ("payload", "scenario")
                for item in error.errors()
            ):
                statuses["input_status"] = VerificationStatus.FAILED
                issues.append(
                    VerificationIssue(
                        code="missing_required_replay_input",
                        category=VerificationCategory.INPUT,
                        message="Receipt is missing the complete scenario replay input.",
                    )
                )
        else:
            issues.append(
                VerificationIssue(
                    code="malformed_receipt",
                    category=VerificationCategory.SCHEMA,
                    message=str(error),
                )
            )
        return _report(statuses, issues, None, started_ns)

    statuses["schema_status"] = VerificationStatus.PASSED
    payload = parsed.payload
    versions_supported = _check_versions(payload, issues)
    statuses["version_status"] = (
        VerificationStatus.PASSED if versions_supported else VerificationStatus.FAILED
    )

    digest_supported = (
        parsed.integrity.algorithm == "sha256"
        and payload.canonicalization_version == CANONICALIZATION_VERSION
    )
    verified_digest: str | None = None
    if not digest_supported:
        statuses["integrity_status"] = VerificationStatus.FAILED
        issues.append(
            VerificationIssue(
                code="unsupported_digest_method",
                category=VerificationCategory.INTEGRITY,
                message=(
                    "Only SHA-256 with the supported LIFELINE JSON canonicalization "
                    "can be checked."
                ),
            )
        )
    else:
        try:
            verified_digest = hashlib.sha256(
                canonical_payload_bytes(payload)
            ).hexdigest()
        except (TypeError, ValueError) as error:
            statuses["integrity_status"] = VerificationStatus.FAILED
            issues.append(
                VerificationIssue(
                    code="payload_not_canonicalizable",
                    category=VerificationCategory.INTEGRITY,
                    message=f"Receipt payload is not canonical JSON: {error}",
                )
            )
        else:
            digest_matches = hmac.compare_digest(
                verified_digest,
                parsed.integrity.digest,
            )
            statuses["integrity_status"] = (
                VerificationStatus.PASSED
                if digest_matches
                else VerificationStatus.FAILED
            )
            if not digest_matches:
                issues.append(
                    VerificationIssue(
                        code="payload_digest_mismatch",
                        category=VerificationCategory.INTEGRITY,
                        message="SHA-256 does not match the canonical receipt payload.",
                    )
                )

    scenario = _validate_inputs(payload, issues)
    statuses["input_status"] = (
        VerificationStatus.PASSED
        if scenario is not None
        else VerificationStatus.FAILED
    )

    replay_summary: PlanSummary | None = None
    if scenario is not None and payload.simulation_model_version == SIMULATION_MODEL_VERSION:
        try:
            replay_scenario = _scenario_with_plan(
                scenario,
                payload.recommended_plan.interventions,
            )
            replay = simulate(replay_scenario)
            replay_summary = _summary_from_trace(
                scenario,
                payload.recommended_plan.interventions,
                replay,
            )
            if not _simulator_metrics_agree(
                replay,
                replay_summary,
            ):
                issues.append(
                    VerificationIssue(
                        code="simulator_trace_metric_disagreement",
                        category=VerificationCategory.REPLAY,
                        message=(
                            "Metrics derived independently from the state trace "
                            "disagree with the simulator's reported metrics."
                        ),
                    )
                )
            if replay.steps != payload.selected_trace:
                issues.append(
                    VerificationIssue(
                        code="selected_trace_mismatch",
                        category=VerificationCategory.REPLAY,
                        message="Recorded selected trace differs from deterministic replay.",
                    )
                )
            if replay_summary != payload.recommended_plan:
                issues.append(
                    VerificationIssue(
                        code="selected_outcome_mismatch",
                        category=VerificationCategory.REPLAY,
                        message=(
                            "Replayed assignments, objective, demand metrics, or "
                            "coverage differ from the recommended plan."
                        ),
                    )
                )
            statuses["replay_status"] = (
                VerificationStatus.PASSED
                if not any(issue.category == VerificationCategory.REPLAY for issue in issues)
                else VerificationStatus.FAILED
            )
        except ValidationError as error:
            statuses["replay_status"] = VerificationStatus.FAILED
            statuses["input_status"] = VerificationStatus.FAILED
            issues.extend(_validation_issues(error, VerificationCategory.INPUT))
            issues.append(
                VerificationIssue(
                    code="invalid_recommended_assignment",
                    category=VerificationCategory.INPUT,
                    message=(
                        "Recommended assignments violate scenario resource, target, "
                        "capability, route, timing, or uniqueness constraints."
                    ),
                )
            )
        except (KeyError, StopIteration, ValueError) as error:
            statuses["replay_status"] = VerificationStatus.FAILED
            issues.append(
                VerificationIssue(
                    code="selected_plan_replay_failed",
                    category=VerificationCategory.REPLAY,
                    message=f"Selected plan could not be replayed: {error}",
                )
            )

    if (
        scenario is not None
        and replay_summary is not None
        and payload.simulation_model_version == SIMULATION_MODEL_VERSION
        and payload.optimizer_version == OPTIMIZER_VERSION
    ):
        try:
            baseline_ok = _verify_baselines(
                scenario,
                replay_summary,
                payload.baseline_comparisons,
                issues,
            )
            statuses["baseline_status"] = (
                VerificationStatus.PASSED
                if baseline_ok
                else VerificationStatus.FAILED
            )
        except (KeyError, StopIteration, ValueError, ValidationError) as error:
            statuses["baseline_status"] = VerificationStatus.FAILED
            issues.append(
                VerificationIssue(
                    code="baseline_recomputation_failed",
                    category=VerificationCategory.BASELINE,
                    message=f"Could not independently recompute baselines: {error}",
                )
            )

    if (
        scenario is not None
        and replay_summary is not None
        and versions_supported
    ):
        try:
            optimality_ok = _verify_optimality(
                scenario,
                payload.optimization_policy,
                replay_summary,
                payload.search,
                issues,
            )
            statuses["optimality_status"] = (
                VerificationStatus.PASSED
                if optimality_ok
                else VerificationStatus.FAILED
            )
        except (KeyError, StopIteration, ValueError, ValidationError) as error:
            statuses["optimality_status"] = VerificationStatus.FAILED
            issues.append(
                VerificationIssue(
                    code="optimality_recomputation_failed",
                    category=VerificationCategory.OPTIMALITY,
                    message=f"Could not independently enumerate plans: {error}",
                )
            )

    if not versions_supported:
        for field in ("replay_status", "baseline_status", "optimality_status"):
            if statuses[field] == VerificationStatus.NOT_CHECKED:
                issues.append(
                    VerificationIssue(
                        code="unsupported_version_semantics",
                        category=VerificationCategory.VERSION,
                        message=f"{field.removesuffix('_status')} was not checked.",
                    )
                )

    return _report(statuses, issues, verified_digest, started_ns)


def _parse_receipt(
    receipt: DecisionReceipt | str | bytes | Mapping[str, Any],
) -> DecisionReceipt:
    if isinstance(receipt, DecisionReceipt):
        return receipt
    if isinstance(receipt, bytes):
        raw = json.loads(
            receipt.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_non_finite,
        )
    elif isinstance(receipt, str):
        raw = json.loads(
            receipt,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_non_finite,
        )
    elif isinstance(receipt, Mapping):
        raw = dict(receipt)
    else:
        raise TypeError("receipt must be a DecisionReceipt, JSON string/bytes, or mapping")
    return DecisionReceipt.model_validate(raw)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not permitted: {value}")


def _check_versions(
    payload: ReceiptPayload,
    issues: list[VerificationIssue],
) -> bool:
    versions = (
        ("schema_version", payload.schema_version, RECEIPT_SCHEMA_VERSION),
        (
            "canonicalization_version",
            payload.canonicalization_version,
            CANONICALIZATION_VERSION,
        ),
        (
            "simulation_model_version",
            payload.simulation_model_version,
            SIMULATION_MODEL_VERSION,
        ),
        ("optimizer_version", payload.optimizer_version, OPTIMIZER_VERSION),
    )
    supported = True
    for name, actual, expected in versions:
        if actual != expected:
            supported = False
            issues.append(
                VerificationIssue(
                    code=f"unsupported_{name}",
                    category=VerificationCategory.VERSION,
                    message=f"{name} {actual!r} is unsupported; expected {expected!r}.",
                )
            )
    return supported


def _validate_inputs(
    payload: ReceiptPayload,
    issues: list[VerificationIssue],
) -> Scenario | None:
    valid = True
    try:
        scenario = Scenario.model_validate(payload.scenario)
    except ValidationError as error:
        issues.extend(_validation_issues(error, VerificationCategory.INPUT))
        issues.append(
            VerificationIssue(
                code="invalid_scenario_inputs",
                category=VerificationCategory.INPUT,
                message="Included scenario is incomplete or violates the model contract.",
            )
        )
        return None

    if scenario.interventions:
        valid = False
        issues.append(
            VerificationIssue(
                code="scenario_has_preassigned_interventions",
                category=VerificationCategory.INPUT,
                message="Optimization replay inputs must not contain committed assignments.",
            )
        )
    if not scenario.demands:
        valid = False
        issues.append(
            VerificationIssue(
                code="scenario_has_no_demands",
                category=VerificationCategory.INPUT,
                message="At least one explicit demand is required for optimization.",
            )
        )
    if any(
        intervention.dispatch_minute != RESOURCE_CONSTRAINTS.dispatch_minute
        or intervention.duration_minutes is not None
        for intervention in payload.recommended_plan.interventions
    ):
        valid = False
        issues.append(
            VerificationIssue(
                code="unsupported_recommended_action_timing",
                category=VerificationCategory.INPUT,
                message=(
                    "Optimizer plans dispatch at minute 0 and support each target "
                    "through the scenario horizon."
                ),
            )
        )
    if payload.resource_constraints != RESOURCE_CONSTRAINTS:
        valid = False
        issues.append(
            VerificationIssue(
                code="unsupported_resource_constraints",
                category=VerificationCategory.INPUT,
                message="Recorded resource constraints do not match optimizer version 1.0.",
            )
        )
    if payload.metric_definitions != METRIC_DEFINITIONS:
        valid = False
        issues.append(
            VerificationIssue(
                code="metric_definitions_mismatch",
                category=VerificationCategory.INPUT,
                message="Metric units or formulas differ from the supported definitions.",
            )
        )
    if payload.assumptions != MODEL_ASSUMPTIONS:
        valid = False
        issues.append(
            VerificationIssue(
                code="assumptions_mismatch",
                category=VerificationCategory.INPUT,
                message="Recorded assumptions differ from the supported model assumptions.",
            )
        )
    if payload.limitations != MODEL_LIMITATIONS:
        valid = False
        issues.append(
            VerificationIssue(
                code="limitations_mismatch",
                category=VerificationCategory.INPUT,
                message="Recorded limitations differ from the supported model limitations.",
            )
        )
    return scenario if valid else None


def _scenario_with_plan(
    scenario: Scenario,
    interventions: tuple[Intervention, ...],
) -> Scenario:
    return Scenario.model_validate(
        {
            "id": scenario.id,
            "horizon_minutes": scenario.horizon_minutes,
            "assets": scenario.assets,
            "demands": scenario.demands,
            "faults": scenario.faults,
            "resources": scenario.resources,
            "interventions": interventions,
        }
    )


def _summary_from_trace(
    scenario: Scenario,
    interventions: tuple[Intervention, ...],
    replay: SimulationResult,
) -> PlanSummary:
    if len(replay.steps) != scenario.horizon_minutes + 1:
        raise ValueError("simulator trace has an unexpected number of boundaries")

    metrics: list[DemandMetric] = []
    for demand in scenario.demands:
        served = 0
        for step in replay.steps[:-1]:
            states = {state.asset_id: state.service_available for state in step.assets}
            if states[demand.served_by_asset_id]:
                served += 1
        possible_person_minutes = demand.population * scenario.horizon_minutes
        service_person_minutes = demand.population * served
        metrics.append(
            DemandMetric(
                demand_id=demand.id,
                community_id=demand.community_id,
                service_type=demand.service_type,
                population=demand.population,
                served_minutes=served,
                service_person_minutes=service_person_minutes,
                total_service_person_minutes=possible_person_minutes,
                coverage_parts_per_million=(
                    service_person_minutes * _PPM // possible_person_minutes
                ),
                priority_weight=demand.priority_weight,
                weighted_service_person_minutes=(
                    service_person_minutes * demand.priority_weight
                ),
            )
        )
    demand_metrics = tuple(metrics)
    coverages = tuple(
        CommunityServiceCoverage(
            demand_id=metric.demand_id,
            community_id=metric.community_id,
            service_type=metric.service_type,
            weighted_service_person_minutes=metric.weighted_service_person_minutes,
            total_weighted_service_person_minutes=(
                metric.total_service_person_minutes * metric.priority_weight
            ),
            coverage_parts_per_million=metric.coverage_parts_per_million,
        )
        for metric in sorted(demand_metrics, key=lambda item: item.demand_id)
    )
    resources = {resource.id: resource for resource in scenario.resources}
    deployment_minutes = 0
    for intervention in interventions:
        route = next(
            route
            for route in resources[intervention.resource_id].travel_times
            if route.asset_id == intervention.target_asset_id
        )
        deployment_minutes += route.travel_minutes + route.setup_minutes
    assigned = {intervention.resource_id for intervention in interventions}
    plan_id = json.dumps(
        [
            [
                intervention.resource_id,
                intervention.target_asset_id,
                intervention.dependency_group_id,
            ]
            for intervention in sorted(interventions, key=lambda item: item.resource_id)
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return PlanSummary(
        plan_id=plan_id,
        interventions=tuple(sorted(interventions, key=lambda item: item.resource_id)),
        idle_resource_ids=tuple(
            sorted(resource.id for resource in scenario.resources if resource.id not in assigned)
        ),
        objective=ObjectiveValue(
            weighted_service_person_minutes=sum(
                metric.weighted_service_person_minutes for metric in demand_metrics
            ),
            minimum_community_service_coverage_ppm=min(
                coverage.coverage_parts_per_million for coverage in coverages
            ),
            deployment_minutes=deployment_minutes,
            intervention_count=len(interventions),
        ),
        demand_metrics=demand_metrics,
        community_service_coverages=coverages,
    )


def _simulator_metrics_agree(
    replay: SimulationResult,
    expected: PlanSummary,
) -> bool:
    """Cross-check simulator aggregates against independently counted trace metrics."""
    simulator_metrics = replay.demand_metrics
    if simulator_metrics != expected.demand_metrics:
        return False
    if (
        replay.total_weighted_service_person_minutes
        != expected.objective.weighted_service_person_minutes
    ):
        return False
    if replay.total_service_person_minutes != sum(
        metric.service_person_minutes for metric in expected.demand_metrics
    ):
        return False
    if replay.total_possible_service_person_minutes != sum(
        metric.total_service_person_minutes for metric in expected.demand_metrics
    ):
        return False
    return True


def _candidate_actions(
    scenario: Scenario,
) -> dict[str, tuple[_Candidate, ...]]:
    weighted_demand_by_asset: dict[str, int] = {}
    for demand in scenario.demands:
        weighted_demand_by_asset[demand.served_by_asset_id] = (
            weighted_demand_by_asset.get(demand.served_by_asset_id, 0)
            + demand.population * demand.priority_weight
        )

    result: dict[str, tuple[_Candidate, ...]] = {}
    for resource in sorted(scenario.resources, key=lambda item: item.id):
        routes_by_target = {route.asset_id: route for route in resource.travel_times}
        actions: list[_Candidate] = []
        for asset in sorted(scenario.assets, key=lambda item: item.id):
            route = routes_by_target.get(asset.id)
            if route is None:
                continue
            if route.travel_minutes + route.setup_minutes >= scenario.horizon_minutes:
                continue
            for group in sorted(asset.dependency_groups, key=lambda item: item.id):
                if group.service_type not in resource.capabilities:
                    continue
                actions.append(
                    _Candidate(
                        resource_id=resource.id,
                        target_asset_id=asset.id,
                        dependency_group_id=group.id,
                        travel_minutes=route.travel_minutes,
                        setup_minutes=route.setup_minutes,
                        direct_priority=weighted_demand_by_asset.get(asset.id, 0),
                    )
                )
        result[resource.id] = tuple(
            sorted(
                actions,
                key=lambda action: (
                    action.resource_id,
                    action.target_asset_id,
                    action.dependency_group_id,
                ),
            )
        )
    return result


def _action_sets(
    scenario: Scenario,
    actions: dict[str, tuple[_Candidate, ...]],
):
    resources = sorted(scenario.resources, key=lambda item: item.id)
    choices = [(None, *actions[resource.id]) for resource in resources]
    return itertools.product(*choices)


def _valid_action_set(actions: tuple[_Candidate, ...]) -> bool:
    targets = [action.dependency_group_id for action in actions]
    return len(targets) == len(set(targets))


def _interventions(actions: tuple[_Candidate, ...]) -> tuple[Intervention, ...]:
    return tuple(
        action.as_intervention()
        for action in sorted(actions, key=lambda item: item.resource_id)
    )


def _within_tolerance(score: int, best: int, tolerance_ppm: int) -> bool:
    return score * _PPM >= best * (_PPM - tolerance_ppm)


def _verify_baselines(
    scenario: Scenario,
    selected_plan: PlanSummary,
    recorded: tuple[BaselineComparison, ...],
    issues: list[VerificationIssue],
) -> bool:
    actions = _candidate_actions(scenario)
    flat = tuple(
        action
        for resource_id in sorted(actions)
        for action in actions[resource_id]
    )
    assignments = (
        (),
        _static_priority_baseline(flat),
        _greedy_baseline(scenario, flat),
    )
    expected: list[BaselineComparison] = []
    for name, interventions in zip(_EXPECTED_BASELINES, assignments, strict=True):
        plan_scenario = _scenario_with_plan(scenario, interventions)
        replay = simulate(plan_scenario)
        summary = _summary_from_trace(scenario, interventions, replay)
        expected.append(
            BaselineComparison(
                baseline=name,
                plan=summary,
                primary_score_delta=(
                    selected_plan.objective.weighted_service_person_minutes
                    - summary.objective.weighted_service_person_minutes
                ),
                minimum_community_service_coverage_delta_ppm=(
                    selected_plan.objective.minimum_community_service_coverage_ppm
                    - summary.objective.minimum_community_service_coverage_ppm
                ),
            )
        )
    if recorded != tuple(expected):
        issues.append(
            VerificationIssue(
                code="baseline_comparison_mismatch",
                category=VerificationCategory.BASELINE,
                message=(
                    "Recomputed baseline assignments, outcomes, or deltas differ "
                    "from the receipt."
                ),
            )
        )
        return False
    if tuple(item.baseline for item in recorded) != _EXPECTED_BASELINES:
        issues.append(
            VerificationIssue(
                code="baseline_set_or_order_mismatch",
                category=VerificationCategory.BASELINE,
                message="Receipt must contain each supported baseline exactly once and in order.",
            )
        )
        return False
    return True


def _static_priority_baseline(
    candidates: tuple[_Candidate, ...],
) -> tuple[Intervention, ...]:
    ranked = sorted(
        candidates,
        key=lambda action: (
            -action.direct_priority,
            action.deployment_minutes,
            action.resource_id,
            action.target_asset_id,
            action.dependency_group_id,
        ),
    )
    used_resources: set[str] = set()
    used_groups: set[str] = set()
    chosen: list[_Candidate] = []
    for action in ranked:
        if action.direct_priority == 0:
            break
        if action.resource_id in used_resources or action.dependency_group_id in used_groups:
            continue
        used_resources.add(action.resource_id)
        used_groups.add(action.dependency_group_id)
        chosen.append(action)
    return _interventions(tuple(chosen))


def _greedy_baseline(
    scenario: Scenario,
    candidates: tuple[_Candidate, ...],
) -> tuple[Intervention, ...]:
    chosen: list[_Candidate] = []
    used_resources: set[str] = set()
    used_groups: set[str] = set()
    empty_score = _summary_from_trace(
        scenario,
        (),
        simulate(_scenario_with_plan(scenario, ())),
    ).objective.weighted_service_person_minutes
    current_score = empty_score

    while True:
        best: _Candidate | None = None
        best_score = current_score
        for action in candidates:
            if action.resource_id in used_resources or action.dependency_group_id in used_groups:
                continue
            trial = tuple((*chosen, action))
            interventions = _interventions(trial)
            result = simulate(_scenario_with_plan(scenario, interventions))
            score = _summary_from_trace(
                scenario,
                interventions,
                result,
            ).objective.weighted_service_person_minutes
            if score > best_score or (
                score == best_score
                and score > current_score
                and best is not None
                and (
                    action.deployment_minutes,
                    action.resource_id,
                    action.target_asset_id,
                    action.dependency_group_id,
                )
                < (
                    best.deployment_minutes,
                    best.resource_id,
                    best.target_asset_id,
                    best.dependency_group_id,
                )
            ):
                best = action
                best_score = score
        if best is None or best_score <= current_score:
            return _interventions(tuple(chosen))
        chosen.append(best)
        used_resources.add(best.resource_id)
        used_groups.add(best.dependency_group_id)
        current_score = best_score


def _verify_optimality(
    scenario: Scenario,
    policy: OptimizationPolicy,
    selected_plan: PlanSummary,
    search: ReceiptSearchSummary,
    issues: list[VerificationIssue],
) -> bool:
    actions = _candidate_actions(scenario)
    number_of_candidates = 1
    for options in actions.values():
        number_of_candidates *= 1 + len(options)
    if number_of_candidates > policy.max_candidate_plans:
        issues.append(
            VerificationIssue(
                code="candidate_limit_exceeded",
                category=VerificationCategory.OPTIMALITY,
                message=(
                    f"Replay space has {number_of_candidates} candidates, above "
                    f"the declared limit {policy.max_candidate_plans}."
                ),
            )
        )
        return False

    feasible = 0
    best_primary = -1
    for choice in _action_sets(scenario, actions):
        chosen = tuple(action for action in choice if action is not None)
        if not _valid_action_set(chosen):
            continue
        feasible += 1
        intervention_set = _interventions(chosen)
        result = simulate(_scenario_with_plan(scenario, intervention_set))
        score = _summary_from_trace(
            scenario,
            intervention_set,
            result,
        ).objective.weighted_service_person_minutes
        best_primary = max(best_primary, score)

    eligible_count = 0
    best_plan: PlanSummary | None = None
    best_tie_key: tuple[int, int, int, str] | None = None
    for choice in _action_sets(scenario, actions):
        chosen = tuple(action for action in choice if action is not None)
        if not _valid_action_set(chosen):
            continue
        intervention_set = _interventions(chosen)
        result = simulate(_scenario_with_plan(scenario, intervention_set))
        summary = _summary_from_trace(scenario, intervention_set, result)
        score = summary.objective.weighted_service_person_minutes
        if not _within_tolerance(
            score,
            best_primary,
            policy.primary_tolerance_ppm,
        ):
            continue
        eligible_count += 1
        tie_key = (
            -summary.objective.minimum_community_service_coverage_ppm,
            summary.objective.deployment_minutes,
            summary.objective.intervention_count,
            summary.plan_id,
        )
        if best_tie_key is None or tie_key < best_tie_key:
            best_tie_key = tie_key
            best_plan = summary

    expected = (
        number_of_candidates,
        feasible,
        feasible,
        eligible_count,
        best_primary,
        best_plan,
    )
    actual = (
        search.candidate_plans,
        search.feasible_plans,
        search.plans_evaluated,
        search.fairness_eligible_plans,
        search.best_primary_score,
        selected_plan,
    )
    correct = search.exhaustive_search_complete and expected == actual
    selected_score = selected_plan.objective.weighted_service_person_minutes
    claimed_search = (
        search.selected_primary_score,
        search.selected_primary_score_loss,
        search.fairness_tradeoff_applied,
    )
    expected_claim = (
        selected_score,
        best_primary - selected_score,
        selected_score < best_primary,
    )
    if not correct or claimed_search != expected_claim:
        issues.append(
            VerificationIssue(
                code="optimality_evidence_mismatch",
                category=VerificationCategory.OPTIMALITY,
                message=(
                    "Independent enumeration found different plan counts, best score, "
                    "eligible count, selection, or fairness trade-off."
                ),
            )
        )
        return False
    return True


def _validation_issues(
    error: ValidationError,
    category: VerificationCategory,
) -> list[VerificationIssue]:
    issues = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        issues.append(
            VerificationIssue(
                code="contract_validation_error",
                category=category,
                message=f"{location}: {item['msg']}",
            )
        )
    return issues


def _report(
    statuses: dict[str, VerificationStatus],
    issues: list[VerificationIssue],
    digest: str | None,
    started_ns: int,
) -> VerificationReport:
    return VerificationReport(
        valid=all(status == VerificationStatus.PASSED for status in statuses.values()),
        **statuses,
        verified_payload_sha256=digest,
        verification_duration_ns=perf_counter_ns() - started_ns,
        issues=tuple(issues),
    )
