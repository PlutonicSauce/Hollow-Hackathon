"""Exhaustive intervention assignment and comparable baseline policies."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from itertools import product
from time import perf_counter_ns

from .models import (
    BaselineComparison,
    CommunityServiceCoverage,
    DemandMetric,
    Intervention,
    InterventionResource,
    OptimizationPolicy,
    OptimizationResult,
    ObjectiveValue,
    PlanSummary,
    PolicyName,
    Scenario,
    ServiceType,
    SimulationResult,
    TravelTime,
)
from .simulation import simulate

_PPM = 1_000_000


class OptimizationLimitError(ValueError):
    """Raised when an exact search would exceed its declared candidate bound."""


@dataclass(frozen=True)
class _Action:
    intervention: Intervention
    travel_time: TravelTime
    direct_priority: int

    @property
    def resource_id(self) -> str:
        return self.intervention.resource_id

    @property
    def dependency_group_id(self) -> str:
        return self.intervention.dependency_group_id

    @property
    def target_asset_id(self) -> str:
        return self.intervention.target_asset_id

    @property
    def deployment_minutes(self) -> int:
        return self.travel_time.travel_minutes + self.travel_time.setup_minutes


def optimize_interventions(
    scenario: Scenario,
    policy: OptimizationPolicy | None = None,
) -> OptimizationResult:
    """Exhaustively optimize one-shot assignments for a bounded scenario."""
    policy = policy or OptimizationPolicy()
    if not scenario.demands:
        raise ValueError("optimization requires at least one explicit demand")
    if scenario.interventions:
        raise ValueError(
            "optimization requires an uncommitted scenario; pass candidate "
            "resources without preassigned interventions"
        )

    started_ns = perf_counter_ns()
    actions_by_resource = _candidate_actions_by_resource(scenario)
    choices_by_resource = [
        (None, *actions_by_resource[resource.id])
        for resource in sorted(scenario.resources, key=lambda item: item.id)
    ]
    candidate_count = math.prod(len(choices) for choices in choices_by_resource)
    if candidate_count > policy.max_candidate_plans:
        raise OptimizationLimitError(
            f"exact search has {candidate_count} candidate plans, exceeding "
            f"max_candidate_plans={policy.max_candidate_plans}"
        )

    evaluated = 0
    feasible = 0
    best_primary = -1
    fairness_eligible: list[PlanSummary] = []

    for selected in product(*choices_by_resource):
        chosen_actions = tuple(action for action in selected if action is not None)
        if _has_target_conflict(chosen_actions):
            continue

        feasible += 1
        summary = _evaluate_plan(
            scenario,
            tuple(action.intervention for action in chosen_actions),
        )
        evaluated += 1
        primary = summary.objective.weighted_service_person_minutes

        if primary > best_primary:
            best_primary = primary
            fairness_eligible = [
                prior
                for prior in fairness_eligible
                if _within_primary_tolerance(
                    prior.objective.weighted_service_person_minutes,
                    best_primary,
                    policy.primary_tolerance_ppm,
                )
            ]
        if _within_primary_tolerance(
            primary,
            best_primary,
            policy.primary_tolerance_ppm,
        ):
            fairness_eligible.append(summary)

    if not fairness_eligible:
        raise RuntimeError("exhaustive search produced no feasible plan")

    selected_plan = min(
        fairness_eligible,
        key=lambda plan: (
            -plan.objective.minimum_community_service_coverage_ppm,
            plan.objective.deployment_minutes,
            plan.objective.intervention_count,
            plan.plan_id,
        ),
    )
    computation_time_ns = perf_counter_ns() - started_ns

    baselines = _baseline_comparisons(scenario, actions_by_resource, selected_plan)
    return OptimizationResult(
        policy=policy,
        candidate_plans=candidate_count,
        feasible_plans=feasible,
        plans_evaluated=evaluated,
        fairness_eligible_plans=len(fairness_eligible),
        exhaustive_search_complete=True,
        best_primary_score=best_primary,
        selected_plan=selected_plan,
        baseline_comparisons=baselines,
        computation_time_ns=computation_time_ns,
    )


def _candidate_actions_by_resource(
    scenario: Scenario,
) -> dict[str, tuple[_Action, ...]]:
    assets_by_id = {asset.id: asset for asset in scenario.assets}
    direct_priority: dict[str, int] = {}
    for demand in scenario.demands:
        direct_priority[demand.served_by_asset_id] = (
            direct_priority.get(demand.served_by_asset_id, 0)
            + demand.population * demand.priority_weight
        )

    result: dict[str, tuple[_Action, ...]] = {}
    for resource in sorted(scenario.resources, key=lambda item: item.id):
        routes = {route.asset_id: route for route in resource.travel_times}
        actions: list[_Action] = []
        for asset_id in sorted(assets_by_id):
            asset = assets_by_id[asset_id]
            route = routes.get(asset_id)
            if route is None or route.travel_minutes + route.setup_minutes >= scenario.horizon_minutes:
                continue
            for group in sorted(asset.dependency_groups, key=lambda item: item.id):
                if group.service_type not in resource.capabilities:
                    continue
                identity = json.dumps(
                    [resource.id, asset.id, group.id],
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                actions.append(
                    _Action(
                        intervention=Intervention(
                            id=f"assignment:{identity}",
                            resource_id=resource.id,
                            target_asset_id=asset.id,
                            dependency_group_id=group.id,
                            dispatch_minute=0,
                        ),
                        travel_time=route,
                        direct_priority=direct_priority.get(asset.id, 0),
                    )
                )
        result[resource.id] = tuple(
            sorted(actions, key=_action_stable_key)
        )
    return result


def _has_target_conflict(actions: tuple[_Action, ...]) -> bool:
    groups = [action.dependency_group_id for action in actions]
    return len(groups) != len(set(groups))


def _within_primary_tolerance(
    score: int,
    best_score: int,
    tolerance_ppm: int,
) -> bool:
    return score * _PPM >= best_score * (_PPM - tolerance_ppm)


def _evaluate_plan(
    scenario: Scenario,
    interventions: tuple[Intervention, ...],
) -> PlanSummary:
    plan_scenario = Scenario.model_validate(
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
    result = simulate(plan_scenario)
    return _summarize(scenario, interventions, result)


def _summarize(
    scenario: Scenario,
    interventions: tuple[Intervention, ...],
    result: SimulationResult,
) -> PlanSummary:
    resources_by_id = {resource.id: resource for resource in scenario.resources}
    deployment_minutes = 0
    for intervention in interventions:
        resource = resources_by_id[intervention.resource_id]
        route = next(
            item
            for item in resource.travel_times
            if item.asset_id == intervention.target_asset_id
        )
        deployment_minutes += route.travel_minutes + route.setup_minutes

    community_service_coverages = tuple(
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
        for metric in sorted(result.demand_metrics, key=lambda item: item.demand_id)
    )
    minimum_coverage = min(
        coverage.coverage_parts_per_million
        for coverage in community_service_coverages
    )

    assigned_resource_ids = {item.resource_id for item in interventions}
    idle_resource_ids = tuple(
        sorted(
            resource.id
            for resource in scenario.resources
            if resource.id not in assigned_resource_ids
        )
    )
    plan_id = json.dumps(
        [
            [
                item.resource_id,
                item.target_asset_id,
                item.dependency_group_id,
            ]
            for item in sorted(interventions, key=lambda item: item.resource_id)
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return PlanSummary(
        plan_id=plan_id,
        interventions=tuple(sorted(interventions, key=lambda item: item.resource_id)),
        idle_resource_ids=idle_resource_ids,
        objective=ObjectiveValue(
            weighted_service_person_minutes=result.total_weighted_service_person_minutes,
            minimum_community_service_coverage_ppm=minimum_coverage,
            deployment_minutes=deployment_minutes,
            intervention_count=len(interventions),
        ),
        demand_metrics=result.demand_metrics,
        community_service_coverages=community_service_coverages,
    )


def _baseline_comparisons(
    scenario: Scenario,
    actions_by_resource: dict[str, tuple[_Action, ...]],
    selected_plan: PlanSummary,
) -> tuple[BaselineComparison, ...]:
    candidates = tuple(
        action
        for resource_id in sorted(actions_by_resource)
        for action in actions_by_resource[resource_id]
    )
    baseline_plans = (
        (PolicyName.NO_INTERVENTION, ()),
        (
            PolicyName.STATIC_PRIORITY,
            _static_priority_assignments(candidates),
        ),
        (
            PolicyName.GREEDY,
            _greedy_assignments(scenario, candidates),
        ),
    )
    comparisons: list[BaselineComparison] = []
    for name, interventions in baseline_plans:
        summary = _evaluate_plan(scenario, interventions)
        comparisons.append(
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
    return tuple(comparisons)


def _static_priority_assignments(
    candidates: tuple[_Action, ...],
) -> tuple[Intervention, ...]:
    """Prioritize direct weighted demand, ignoring upstream cascade effects."""
    ordered = sorted(
        candidates,
        key=lambda action: (
            -action.direct_priority,
            action.deployment_minutes,
            *_action_stable_key(action),
        ),
    )
    assigned_resources: set[str] = set()
    assigned_groups: set[str] = set()
    assignments: list[Intervention] = []
    for action in ordered:
        if action.direct_priority == 0:
            break
        if (
            action.resource_id in assigned_resources
            or action.dependency_group_id in assigned_groups
        ):
            continue
        assigned_resources.add(action.resource_id)
        assigned_groups.add(action.dependency_group_id)
        assignments.append(action.intervention)
    return tuple(sorted(assignments, key=lambda item: item.resource_id))


def _greedy_assignments(
    scenario: Scenario,
    candidates: tuple[_Action, ...],
) -> tuple[Intervention, ...]:
    """Repeatedly take the feasible action with the largest full-horizon marginal score."""
    assignments: list[Intervention] = []
    used_resources: set[str] = set()
    used_groups: set[str] = set()
    current_score = _evaluate_plan(scenario, ()).objective.weighted_service_person_minutes

    while True:
        best_action: _Action | None = None
        best_score = current_score
        for action in candidates:
            if (
                action.resource_id in used_resources
                or action.dependency_group_id in used_groups
            ):
                continue
            trial = tuple((*assignments, action.intervention))
            score = _evaluate_plan(scenario, trial).objective.weighted_service_person_minutes
            if score > best_score or (
                score == best_score
                and score > current_score
                and best_action is not None
                and (
                    action.deployment_minutes,
                    *_action_stable_key(action),
                )
                < (
                    best_action.deployment_minutes,
                    *_action_stable_key(best_action),
                )
            ):
                best_action = action
                best_score = score

        if best_action is None or best_score <= current_score:
            break
        assignments.append(best_action.intervention)
        used_resources.add(best_action.resource_id)
        used_groups.add(best_action.dependency_group_id)
        current_score = best_score

    return tuple(sorted(assignments, key=lambda item: item.resource_id))


def _action_stable_key(action: _Action) -> tuple[str, str, str]:
    return (
        action.resource_id,
        action.target_asset_id,
        action.dependency_group_id,
    )
