import unittest

from pydantic import ValidationError

from engine.models import (
    AssetKind,
    BufferSpec,
    DependencyGroup,
    FaultEvent,
    InfrastructureAsset,
    Intervention,
    InterventionResource,
    Scenario,
    ServiceType,
    TravelTime,
)
from engine.scenarios import hand_calculated_scenario


def _asset(
    asset_id: str,
    service: ServiceType,
    groups: tuple[DependencyGroup, ...] = (),
) -> InfrastructureAsset:
    return InfrastructureAsset(
        id=asset_id,
        name=asset_id,
        kind=AssetKind.SOURCE if not groups else AssetKind.FACILITY,
        provides=service,
        dependency_groups=groups,
        buffer=BufferSpec(
            unit="reserve_unit",
            capacity_units=0,
            initial_units=0,
            depletion_units_per_minute=0,
            recovery_units_per_minute=0,
        ),
    )


class ContractValidationTests(unittest.TestCase):
    def test_synthetic_scenario_is_valid_and_topologically_ordered(self) -> None:
        scenario = hand_calculated_scenario()
        order = scenario.topological_asset_ids()
        self.assertLess(order.index("grid"), order.index("pump"))
        self.assertLess(order.index("pump"), order.index("scrubber"))

    def test_scenario_round_trips_through_json_validation(self) -> None:
        scenario = hand_calculated_scenario()
        restored = Scenario.model_validate_json(scenario.model_dump_json())
        self.assertEqual(restored, scenario)

    def test_missing_provider_reference_is_rejected(self) -> None:
        dependent = _asset(
            "pump",
            ServiceType.WATER,
            (
                DependencyGroup(
                    id="power",
                    service_type=ServiceType.POWER,
                    provider_asset_ids=("missing-grid",),
                ),
            ),
        )
        with self.assertRaisesRegex(ValidationError, "unknown provider"):
            Scenario(id="missing-ref", horizon_minutes=3, assets=(dependent,))

    def test_demand_with_missing_asset_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unknown asset"):
            Scenario.model_validate(
                {
                    "id": "missing-demand-asset",
                    "horizon_minutes": 2,
                    "assets": [
                        {
                            "id": "grid",
                            "name": "Grid",
                            "kind": "source",
                            "provides": "power",
                            "buffer": {
                                "unit": "reserve_unit",
                                "capacity_units": 0,
                                "initial_units": 0,
                                "depletion_units_per_minute": 0,
                                "recovery_units_per_minute": 0,
                            },
                        }
                    ],
                    "demands": [
                        {
                            "id": "demand",
                            "community_id": "community",
                            "served_by_asset_id": "not-there",
                            "service_type": "air",
                            "population": 1,
                            "priority_weight": 1,
                        }
                    ],
                }
            )

    def test_fault_with_missing_asset_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "fault outage references unknown asset"):
            Scenario(
                id="missing-fault-asset",
                horizon_minutes=2,
                assets=(_asset("grid", ServiceType.POWER),),
                faults=(FaultEvent(id="outage", asset_id="missing", start_minute=0),),
            )

    def test_intervention_capability_must_match_target_dependency(self) -> None:
        scenario = hand_calculated_scenario()
        resource = InterventionResource(
            id="water-tanker",
            name="Water tanker",
            capabilities=(ServiceType.WATER,),
            travel_times=(TravelTime(asset_id="scrubber", minutes=0),),
        )
        intervention = Intervention(
            id="wrong-resource",
            resource_id=resource.id,
            target_asset_id="scrubber",
            dependency_group_id="scrubber-power",
            dispatch_minute=0,
        )
        with self.assertRaisesRegex(ValidationError, "cannot provide"):
            Scenario(
                id="invalid-intervention",
                horizon_minutes=scenario.horizon_minutes,
                assets=scenario.assets,
                demands=scenario.demands,
                faults=scenario.faults,
                resources=(resource,),
                interventions=(intervention,),
            )

    def test_invalid_buffer_range_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            BufferSpec(
                unit="reserve_unit",
                capacity_units=1,
                initial_units=2,
                depletion_units_per_minute=1,
                recovery_units_per_minute=1,
            )

    def test_negative_horizon_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Scenario(id="invalid", horizon_minutes=-1, assets=(_asset("grid", ServiceType.POWER),))

    def test_dependency_cycle_is_rejected(self) -> None:
        asset_a = _asset(
            "a",
            ServiceType.POWER,
            (
                DependencyGroup(
                    id="a-needs-b",
                    service_type=ServiceType.POWER,
                    provider_asset_ids=("b",),
                ),
            ),
        )
        asset_b = _asset(
            "b",
            ServiceType.POWER,
            (
                DependencyGroup(
                    id="b-needs-a",
                    service_type=ServiceType.POWER,
                    provider_asset_ids=("a",),
                ),
            ),
        )
        with self.assertRaisesRegex(ValidationError, "acyclic"):
            Scenario(id="cycle", horizon_minutes=2, assets=(asset_a, asset_b))

    def test_provider_service_type_must_match_dependency(self) -> None:
        grid = _asset("grid", ServiceType.POWER)
        pump = _asset(
            "pump",
            ServiceType.WATER,
            (
                DependencyGroup(
                    id="pump-water",
                    service_type=ServiceType.WATER,
                    provider_asset_ids=("grid",),
                ),
            ),
        )
        with self.assertRaisesRegex(ValidationError, "supplies"):
            Scenario(id="wrong-service", horizon_minutes=2, assets=(grid, pump))


if __name__ == "__main__":
    unittest.main()
