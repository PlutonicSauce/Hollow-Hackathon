import unittest

from engine.models import (
    FaultEvent,
    Intervention,
    InterventionResource,
    Scenario,
    ServiceType,
    TravelTime,
)
from engine.scenarios import hand_calculated_scenario
from engine.simulation import simulate


def _asset_with_fault(scenario: Scenario, asset_id: str) -> Scenario:
    return Scenario(
        id=f"{scenario.id}-faulted-{asset_id}",
        horizon_minutes=scenario.horizon_minutes,
        assets=scenario.assets,
        demands=scenario.demands,
        faults=(*scenario.faults, FaultEvent(
            id=f"{asset_id}-physical-fault",
            asset_id=asset_id,
            start_minute=0,
            end_minute=2,
        )),
        resources=scenario.resources,
        interventions=scenario.interventions,
    )


class DeterministicSimulationTests(unittest.TestCase):
    def test_and_or_dependencies_and_reserve_boundaries(self) -> None:
        result = simulate(hand_calculated_scenario())
        by_minute = {
            step.minute: {item.asset_id: item for item in step.assets}
            for step in result.steps
        }

        # Pump power is OR(grid, backup), while the scrubber requires both
        # grid AND pump-water. The pump reserve carries the first outage minute.
        self.assertTrue(by_minute[0]["pump"].service_available)
        self.assertEqual(by_minute[0]["pump"].buffer_units, 1)
        self.assertFalse(by_minute[0]["scrubber"].service_available)
        self.assertEqual(by_minute[1]["pump"].buffer_units, 0)
        self.assertTrue(by_minute[1]["pump"].service_available)
        self.assertFalse(by_minute[1]["scrubber"].service_available)
        self.assertTrue(by_minute[2]["scrubber"].service_available)
        self.assertEqual(by_minute[2]["pump"].buffer_units, 1)
        self.assertEqual(by_minute[3]["pump"].buffer_units, 2)

    def test_hand_calculated_demand_metric(self) -> None:
        result = simulate(hand_calculated_scenario())
        metric = result.demand_metrics[0]
        self.assertEqual(metric.served_minutes, 2)
        self.assertEqual(metric.service_person_minutes, 20)
        self.assertEqual(metric.total_service_person_minutes, 40)
        self.assertEqual(metric.coverage_parts_per_million, 500_000)
        self.assertEqual(metric.weighted_service_person_minutes, 40)

    def test_hand_calculated_trace_matches_every_minute(self) -> None:
        result = simulate(hand_calculated_scenario())
        availability = {
            asset_id: [
                next(asset for asset in step.assets if asset.asset_id == asset_id)
                .service_available
                for step in result.steps
            ]
            for asset_id in ("grid", "backup", "pump", "scrubber")
        }
        pump_reserve = [
            next(asset for asset in step.assets if asset.asset_id == "pump").buffer_units
            for step in result.steps
        ]

        self.assertEqual(availability["grid"], [False, False, True, True, True])
        self.assertEqual(availability["backup"], [False, True, True, True, True])
        self.assertEqual(availability["pump"], [True, True, True, True, True])
        self.assertEqual(availability["scrubber"], [False, False, True, True, True])
        self.assertEqual(pump_reserve, [1, 0, 1, 2, 2])

    def test_repeated_simulation_is_identical(self) -> None:
        scenario = hand_calculated_scenario()
        self.assertEqual(simulate(scenario), simulate(scenario))

    def test_intervention_supplies_only_a_matching_dependency(self) -> None:
        scenario = hand_calculated_scenario()
        resource = InterventionResource(
            id="portable-generator",
            name="Portable generator",
            capabilities=(ServiceType.POWER,),
            travel_times=(TravelTime(asset_id="scrubber", minutes=0),),
        )
        intervention = Intervention(
            id="generator-to-scrubber",
            resource_id=resource.id,
            target_asset_id="scrubber",
            dependency_group_id="scrubber-power",
            dispatch_minute=0,
            setup_minutes=0,
        )
        with_backup = Scenario(
            id="with-backup",
            horizon_minutes=scenario.horizon_minutes,
            assets=scenario.assets,
            demands=scenario.demands,
            faults=scenario.faults,
            resources=(resource,),
            interventions=(intervention,),
        )

        result = simulate(with_backup)
        self.assertEqual(result.demand_metrics[0].served_minutes, 4)
        self.assertFalse(
            next(
                asset
                for asset in result.steps[0].assets
                if asset.asset_id == "grid"
            ).service_available
        )

    def test_backup_does_not_clear_a_physical_fault(self) -> None:
        scenario = hand_calculated_scenario()
        resource = InterventionResource(
            id="portable-generator",
            name="Portable generator",
            capabilities=(ServiceType.POWER,),
            travel_times=(TravelTime(asset_id="pump", minutes=0),),
        )
        intervention = Intervention(
            id="generator-to-pump",
            resource_id=resource.id,
            target_asset_id="pump",
            dependency_group_id="pump-power",
            dispatch_minute=0,
        )
        faulted_pump = _asset_with_fault(scenario, "pump")
        with_backup = Scenario(
            id="faulted-pump-with-backup",
            horizon_minutes=faulted_pump.horizon_minutes,
            assets=faulted_pump.assets,
            demands=faulted_pump.demands,
            faults=faulted_pump.faults,
            resources=(resource,),
            interventions=(intervention,),
        )

        first_step = simulate(with_backup).steps[0]
        pump = next(asset for asset in first_step.assets if asset.asset_id == "pump")
        self.assertTrue(pump.physical_fault_active)
        self.assertFalse(pump.service_available)

    def test_fault_intervals_are_half_open(self) -> None:
        result = simulate(hand_calculated_scenario())
        grid_at = {
            step.minute: next(asset for asset in step.assets if asset.asset_id == "grid")
            for step in result.steps
        }
        self.assertTrue(grid_at[1].physical_fault_active)
        self.assertFalse(grid_at[2].physical_fault_active)


if __name__ == "__main__":
    unittest.main()
