import unittest

from pydantic import ValidationError

from engine.models import (
    AssetKind,
    BufferSpec,
    Demand,
    DependencyGroup,
    FaultEvent,
    InfrastructureAsset,
    Intervention,
    InterventionResource,
    OptimizationPolicy,
    PolicyName,
    Scenario,
    ServiceType,
    TravelTime,
)
from engine.optimizer import OptimizationLimitError, optimize_interventions
from engine.scenarios import (
    fairness_tradeoff_scenario,
    downstream_priority_scenario,
    signature_scenario,
)
from engine.simulation import simulate


def _replace_scenario(scenario: Scenario, **updates) -> Scenario:
    data = scenario.model_dump()
    data.update(updates)
    return Scenario.model_validate(data)


def _resource(
    resource_id: str,
    routes: tuple[TravelTime, ...],
    capabilities: tuple[ServiceType, ...] = (ServiceType.POWER,),
) -> InterventionResource:
    return InterventionResource(
        id=resource_id,
        name=resource_id,
        capabilities=capabilities,
        travel_times=routes,
    )


def _set_resource_route(
    scenario: Scenario,
    asset_id: str,
    travel_minutes: int,
    setup_minutes: int,
) -> Scenario:
    resource = scenario.resources[0]
    routes = tuple(
        TravelTime(
            asset_id=route.asset_id,
            travel_minutes=(
                travel_minutes if route.asset_id == asset_id else route.travel_minutes
            ),
            setup_minutes=(
                setup_minutes if route.asset_id == asset_id else route.setup_minutes
            ),
        )
        for route in resource.travel_times
    )
    updated_resource = _resource(resource.id, routes, resource.capabilities)
    return _replace_scenario(scenario, resources=(updated_resource,))


def _two_target_scenario(*, include_specialist: bool = True) -> Scenario:
    no_reserve = BufferSpec(
        unit="reserve_unit",
        capacity_units=0,
        initial_units=0,
        depletion_units_per_minute=0,
        recovery_units_per_minute=0,
    )
    grid = InfrastructureAsset(
        id="grid",
        name="Failed grid",
        kind=AssetKind.SOURCE,
        provides=ServiceType.POWER,
        buffer=no_reserve,
    )
    targets = tuple(
        InfrastructureAsset(
            id=asset_id,
            name=asset_id,
            kind=AssetKind.DEMAND_ENDPOINT,
            provides=ServiceType.MEDICAL,
            dependency_groups=(
                DependencyGroup(
                    id=f"{asset_id}-power",
                    service_type=ServiceType.POWER,
                    provider_asset_ids=("grid",),
                ),
            ),
            buffer=no_reserve,
        )
        for asset_id in ("alpha", "beta")
    )
    resources = [
        _resource(
            "a-flex",
            (
                TravelTime(asset_id="alpha", travel_minutes=0),
                TravelTime(asset_id="beta", travel_minutes=0),
            ),
        )
    ]
    if include_specialist:
        resources.append(
            _resource(
                "b-special",
                (TravelTime(asset_id="alpha", travel_minutes=0),),
            )
        )
    return Scenario(
        id="two-target-assignment",
        horizon_minutes=1,
        assets=(grid, *targets),
        demands=(
            Demand(
                id="alpha-need",
                community_id="alpha-community",
                served_by_asset_id="alpha",
                service_type=ServiceType.MEDICAL,
                population=10,
            ),
            Demand(
                id="beta-need",
                community_id="beta-community",
                served_by_asset_id="beta",
                service_type=ServiceType.MEDICAL,
                population=10,
            ),
        ),
        faults=(FaultEvent(id="grid-down", asset_id="grid", start_minute=0),),
        resources=tuple(resources),
    )


class ExactOptimizerTests(unittest.TestCase):
    def test_zero_available_resources_produces_one_idle_plan(self) -> None:
        scenario = _replace_scenario(signature_scenario(), resources=())
        result = optimize_interventions(scenario)
        self.assertEqual(result.candidate_plans, 1)
        self.assertEqual(result.feasible_plans, 1)
        self.assertEqual(result.plans_evaluated, 1)
        self.assertEqual(result.selected_plan.interventions, ())
        self.assertEqual(result.selected_plan.idle_resource_ids, ())
        self.assertTrue(result.exhaustive_search_complete)

    def test_signature_case_is_hand_solved_and_exact(self) -> None:
        result = optimize_interventions(signature_scenario())
        self.assertEqual(result.candidate_plans, 5)
        self.assertEqual(result.feasible_plans, 5)
        self.assertEqual(result.plans_evaluated, 5)
        self.assertEqual(result.fairness_eligible_plans, 1)
        self.assertTrue(result.exhaustive_search_complete)
        self.assertEqual(
            [(item.target_asset_id, item.dependency_group_id)
             for item in result.selected_plan.interventions],
            [("deep-pump", "pump-power")],
        )
        self.assertEqual(
            result.selected_plan.objective.weighted_service_person_minutes,
            1_080,
        )
        self.assertEqual(
            result.selected_plan.objective.minimum_community_service_coverage_ppm,
            750_000,
        )

    def test_signature_single_action_scores_match_hand_calculation(self) -> None:
        scenario = signature_scenario()
        scores = {"idle": simulate(scenario).total_weighted_service_person_minutes}

        for asset in scenario.assets:
            for group in asset.dependency_groups:
                if group.service_type not in scenario.resources[0].capabilities:
                    continue
                intervention = Intervention(
                    id="manual-single-action",
                    resource_id=scenario.resources[0].id,
                    target_asset_id=asset.id,
                    dependency_group_id=group.id,
                    dispatch_minute=0,
                )
                planned = _replace_scenario(scenario, interventions=(intervention,))
                scores[group.id] = simulate(
                    planned
                ).total_weighted_service_person_minutes

        self.assertEqual(
            scores,
            {
                "idle": 720,
                "pump-power": 1_080,
                "battery-grid-input": 720,
                "scrubber-power": 720,
                "clinic-power": 920,
            },
        )

    def test_static_baselines_use_same_scenario_and_show_tradeoffs(self) -> None:
        result = optimize_interventions(signature_scenario())
        comparisons = {item.baseline: item for item in result.baseline_comparisons}
        self.assertEqual(
            set(comparisons),
            {
                PolicyName.NO_INTERVENTION,
                PolicyName.STATIC_PRIORITY,
                PolicyName.GREEDY,
            },
        )
        self.assertEqual(
            comparisons[PolicyName.NO_INTERVENTION]
            .plan.objective.weighted_service_person_minutes,
            720,
        )
        self.assertEqual(
            comparisons[PolicyName.STATIC_PRIORITY]
            .plan.objective.weighted_service_person_minutes,
            920,
        )
        self.assertEqual(
            comparisons[PolicyName.STATIC_PRIORITY].plan.interventions[0].target_asset_id,
            "clinic",
        )
        self.assertEqual(
            comparisons[PolicyName.GREEDY]
            .plan.objective.weighted_service_person_minutes,
            1_080,
        )
        self.assertEqual(comparisons[PolicyName.NO_INTERVENTION].primary_score_delta, 360)
        self.assertEqual(comparisons[PolicyName.STATIC_PRIORITY].primary_score_delta, 160)
        self.assertEqual(
            comparisons[PolicyName.STATIC_PRIORITY]
            .minimum_community_service_coverage_delta_ppm,
            500_000,
        )
        for comparison in comparisons.values():
            self.assertEqual(
                comparison.plan.demand_metrics[0].total_service_person_minutes,
                160,
            )
            self.assertEqual(
                comparison.plan.demand_metrics[1].total_service_person_minutes,
                80,
            )

    def test_more_resources_create_real_competing_assignments(self) -> None:
        scenario = signature_scenario()
        resource_b = _resource(
            "mobile-generator-b",
            scenario.resources[0].travel_times,
        )
        scenario = _replace_scenario(
            scenario,
            resources=(*scenario.resources, resource_b),
        )
        result = optimize_interventions(scenario)
        self.assertEqual(result.candidate_plans, 25)
        self.assertEqual(result.feasible_plans, 21)
        self.assertEqual(result.plans_evaluated, 21)
        self.assertEqual(
            result.selected_plan.objective.weighted_service_person_minutes,
            1_280,
        )
        self.assertEqual(
            {item.dependency_group_id for item in result.selected_plan.interventions},
            {"pump-power", "clinic-power"},
        )

    def test_incompatible_resource_has_no_non_idle_candidate(self) -> None:
        scenario = signature_scenario()
        resource = _resource(
            "medical-kit",
            (TravelTime(asset_id="clinic", travel_minutes=0),),
            capabilities=(ServiceType.MEDICAL,),
        )
        result = optimize_interventions(_replace_scenario(scenario, resources=(resource,)))
        self.assertEqual(result.candidate_plans, 1)
        self.assertEqual(result.feasible_plans, 1)
        self.assertEqual(result.selected_plan.interventions, ())
        self.assertEqual(result.selected_plan.idle_resource_ids, ("medical-kit",))

    def test_optimizer_rejects_redundant_target_assignments(self) -> None:
        scenario = signature_scenario()
        resource_b = _resource(
            "mobile-generator-b",
            scenario.resources[0].travel_times,
        )
        scenario = _replace_scenario(
            scenario,
            resources=(*scenario.resources, resource_b),
        )
        result = optimize_interventions(scenario)
        # 25 combinations include four pairs assigned to the same group.
        self.assertEqual(result.candidate_plans - result.feasible_plans, 4)
        self.assertTrue(
            len(
                {
                    item.dependency_group_id
                    for item in result.selected_plan.interventions
                }
            )
            == len(result.selected_plan.interventions)
        )

    def test_no_benefit_prefers_idle_resource(self) -> None:
        scenario = _replace_scenario(signature_scenario(), faults=())
        result = optimize_interventions(scenario)
        self.assertEqual(result.selected_plan.interventions, ())
        self.assertEqual(result.selected_plan.objective.deployment_minutes, 0)
        self.assertTrue(
            all(item.primary_score_delta == 0 for item in result.baseline_comparisons)
        )

    def test_equal_scoring_plans_use_stable_plan_id_tie_break(self) -> None:
        scenario = _two_target_scenario(include_specialist=False)
        first = optimize_interventions(scenario)
        second = optimize_interventions(scenario)
        self.assertEqual(first.selected_plan.plan_id, second.selected_plan.plan_id)
        self.assertEqual(
            first.selected_plan.interventions[0].target_asset_id,
            "alpha",
        )

    def test_fairness_tolerance_can_trade_primary_score_for_worst_community(self) -> None:
        result = optimize_interventions(
            fairness_tradeoff_scenario(),
            OptimizationPolicy(primary_tolerance_ppm=400_000),
        )
        self.assertEqual(result.best_primary_score, 200)
        self.assertEqual(result.selected_plan.interventions[0].target_asset_id, "south")
        self.assertEqual(
            result.selected_plan.objective.weighted_service_person_minutes,
            120,
        )
        self.assertEqual(
            result.selected_plan.objective.minimum_community_service_coverage_ppm,
            500_000,
        )
        self.assertEqual(result.fairness_eligible_plans, 2)

    def test_fairness_reports_community_service_needs_separately(self) -> None:
        scenario = signature_scenario()
        demands = tuple(
            Demand(
                id=demand.id,
                community_id="shared-community",
                served_by_asset_id=demand.served_by_asset_id,
                service_type=demand.service_type,
                population=demand.population,
                priority_weight=demand.priority_weight,
            )
            for demand in scenario.demands
        )
        result = optimize_interventions(_replace_scenario(scenario, demands=demands))

        self.assertEqual(len(result.selected_plan.community_service_coverages), 2)
        self.assertEqual(
            {
                coverage.service_type
                for coverage in result.selected_plan.community_service_coverages
            },
            {ServiceType.AIR, ServiceType.MEDICAL},
        )
        self.assertEqual(
            {
                coverage.community_id
                for coverage in result.selected_plan.community_service_coverages
            },
            {"shared-community"},
        )
        self.assertEqual(
            {coverage.demand_id for coverage in result.selected_plan.community_service_coverages},
            {"shelter-air", "clinic-medical"},
        )

    def test_downstream_is_best_when_demand_distribution_changes(self) -> None:
        result = optimize_interventions(downstream_priority_scenario())
        self.assertEqual(
            result.selected_plan.interventions[0].target_asset_id,
            "clinic",
        )
        self.assertEqual(
            result.selected_plan.objective.weighted_service_person_minutes,
            40_001,
        )

    def test_later_travel_and_setup_can_change_the_recommended_target(self) -> None:
        timely = optimize_interventions(signature_scenario())
        delayed_scenario = _set_resource_route(
            signature_scenario(),
            "deep-pump",
            travel_minutes=1,
            setup_minutes=2,
        )
        delayed = optimize_interventions(delayed_scenario)

        self.assertEqual(
            timely.selected_plan.interventions[0].target_asset_id,
            "deep-pump",
        )
        self.assertEqual(
            delayed.selected_plan.interventions[0].target_asset_id,
            "clinic",
        )
        self.assertLess(
            delayed.selected_plan.objective.weighted_service_person_minutes,
            timely.selected_plan.objective.weighted_service_person_minutes,
        )
        self.assertEqual(
            delayed.selected_plan.objective.weighted_service_person_minutes,
            920,
        )

    def test_greedy_can_be_suboptimal_for_competing_resources(self) -> None:
        result = optimize_interventions(_two_target_scenario())
        comparisons = {item.baseline: item for item in result.baseline_comparisons}
        self.assertEqual(
            result.selected_plan.objective.weighted_service_person_minutes,
            20,
        )
        self.assertEqual(
            comparisons[PolicyName.GREEDY]
            .plan.objective.weighted_service_person_minutes,
            10,
        )
        self.assertEqual(comparisons[PolicyName.GREEDY].primary_score_delta, 10)

    def test_repeated_runs_preserve_plan_and_objective(self) -> None:
        scenario = signature_scenario()
        first = optimize_interventions(scenario)
        second = optimize_interventions(scenario)
        self.assertEqual(first.selected_plan, second.selected_plan)
        self.assertEqual(first.baseline_comparisons, second.baseline_comparisons)
        self.assertEqual(first.plans_evaluated, second.plans_evaluated)

    def test_search_limit_fails_explicitly_without_partial_result(self) -> None:
        with self.assertRaises(OptimizationLimitError):
            optimize_interventions(
                signature_scenario(),
                OptimizationPolicy(max_candidate_plans=4),
            )

    def test_optimizer_requires_demands_and_no_preassigned_actions(self) -> None:
        scenario = signature_scenario()
        with self.assertRaisesRegex(ValueError, "at least one explicit demand"):
            optimize_interventions(_replace_scenario(scenario, demands=()))
        committed = Intervention(
            id="committed",
            resource_id="mobile-generator",
            target_asset_id="deep-pump",
            dependency_group_id="pump-power",
            dispatch_minute=0,
        )
        with self.assertRaisesRegex(ValueError, "uncommitted scenario"):
            optimize_interventions(
                _replace_scenario(scenario, interventions=(committed,))
            )


if __name__ == "__main__":
    unittest.main()
