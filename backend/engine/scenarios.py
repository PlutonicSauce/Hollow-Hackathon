"""Small synthetic fixtures used for hand-checking and repeatable tests."""

from .models import (
    AssetKind,
    BufferSpec,
    Demand,
    DependencyGroup,
    FaultEvent,
    InfrastructureAsset,
    Scenario,
    ServiceType,
)


def hand_calculated_scenario() -> Scenario:
    """Return a 4-minute OR/AND cascade with a one-unit pump reserve."""
    no_reserve = BufferSpec(
        unit="reserve_unit",
        capacity_units=0,
        initial_units=0,
        depletion_units_per_minute=0,
        recovery_units_per_minute=0,
    )
    return Scenario(
        id="hand-calculated-or-and",
        horizon_minutes=4,
        assets=(
            InfrastructureAsset(
                id="grid",
                name="Grid feeder",
                kind=AssetKind.SOURCE,
                provides=ServiceType.POWER,
                buffer=no_reserve,
            ),
            InfrastructureAsset(
                id="backup",
                name="Backup power source",
                kind=AssetKind.SOURCE,
                provides=ServiceType.POWER,
                buffer=no_reserve,
            ),
            InfrastructureAsset(
                id="aquifer",
                name="Raw-water source",
                kind=AssetKind.SOURCE,
                provides=ServiceType.WATER,
                buffer=no_reserve,
            ),
            InfrastructureAsset(
                id="pump",
                name="Water pump",
                kind=AssetKind.FACILITY,
                provides=ServiceType.WATER,
                dependency_groups=(
                    DependencyGroup(
                        id="pump-power",
                        service_type=ServiceType.POWER,
                        provider_asset_ids=("grid", "backup"),
                    ),
                    DependencyGroup(
                        id="pump-raw-water",
                        service_type=ServiceType.WATER,
                        provider_asset_ids=("aquifer",),
                    ),
                ),
                buffer=BufferSpec(
                    unit="reserve_unit",
                    capacity_units=2,
                    initial_units=1,
                    depletion_units_per_minute=1,
                    recovery_units_per_minute=1,
                ),
            ),
            InfrastructureAsset(
                id="scrubber",
                name="Air scrubber",
                kind=AssetKind.DEMAND_ENDPOINT,
                provides=ServiceType.AIR,
                dependency_groups=(
                    DependencyGroup(
                        id="scrubber-power",
                        service_type=ServiceType.POWER,
                        provider_asset_ids=("grid",),
                    ),
                    DependencyGroup(
                        id="scrubber-water",
                        service_type=ServiceType.WATER,
                        provider_asset_ids=("pump",),
                    ),
                ),
                buffer=no_reserve,
            ),
        ),
        demands=(
            Demand(
                id="deep-community-air",
                community_id="deep-community",
                served_by_asset_id="scrubber",
                service_type=ServiceType.AIR,
                population=10,
                priority_weight=2,
            ),
        ),
        faults=(
            FaultEvent(
                id="grid-outage",
                asset_id="grid",
                start_minute=0,
                end_minute=2,
            ),
            FaultEvent(
                id="backup-outage",
                asset_id="backup",
                start_minute=0,
                end_minute=1,
            ),
        ),
    )
