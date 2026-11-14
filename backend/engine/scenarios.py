"""Small synthetic fixtures used for hand-checking and repeatable tests."""

from .models import (
    AssetKind,
    BufferSpec,
    Demand,
    DependencyGroup,
    FaultEvent,
    InfrastructureAsset,
    InterventionResource,
    Scenario,
    ServiceType,
    TravelTime,
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


def signature_scenario() -> Scenario:
    """Synthetic generator-routing case where the upstream pump is best."""
    return _generator_routing_scenario(
        scenario_id="hollow-feeder-cascade",
        clinic_population=20,
        clinic_weight=10,
        shelter_population=40,
        shelter_weight=3,
    )


def downstream_priority_scenario() -> Scenario:
    """Same topology with concentrated clinic demand, favoring direct support."""
    return _generator_routing_scenario(
        scenario_id="clinic-priority-cascade",
        clinic_population=1_000,
        clinic_weight=10,
        shelter_population=1,
        shelter_weight=1,
    )


def _generator_routing_scenario(
    *,
    scenario_id: str,
    clinic_population: int,
    clinic_weight: int,
    shelter_population: int,
    shelter_weight: int,
) -> Scenario:
    no_reserve = BufferSpec(
        unit="reserve_unit",
        capacity_units=0,
        initial_units=0,
        depletion_units_per_minute=0,
        recovery_units_per_minute=0,
    )
    return Scenario(
        id=scenario_id,
        horizon_minutes=4,
        assets=(
            InfrastructureAsset(
                id="feeder",
                name="Geothermal power feeder",
                kind=AssetKind.SOURCE,
                provides=ServiceType.POWER,
                buffer=no_reserve,
            ),
            InfrastructureAsset(
                id="raw-water",
                name="Deep aquifer",
                kind=AssetKind.SOURCE,
                provides=ServiceType.WATER,
                buffer=no_reserve,
            ),
            InfrastructureAsset(
                id="deep-pump",
                name="Deep water pump",
                kind=AssetKind.FACILITY,
                provides=ServiceType.WATER,
                dependency_groups=(
                    DependencyGroup(
                        id="pump-power",
                        service_type=ServiceType.POWER,
                        provider_asset_ids=("feeder",),
                    ),
                    DependencyGroup(
                        id="pump-source-water",
                        service_type=ServiceType.WATER,
                        provider_asset_ids=("raw-water",),
                    ),
                ),
                buffer=BufferSpec(
                    unit="reserve_unit",
                    capacity_units=1,
                    initial_units=1,
                    depletion_units_per_minute=1,
                    recovery_units_per_minute=1,
                ),
            ),
            InfrastructureAsset(
                id="scrubber-battery",
                name="Scrubber backup power",
                kind=AssetKind.FACILITY,
                provides=ServiceType.POWER,
                dependency_groups=(
                    DependencyGroup(
                        id="battery-grid-input",
                        service_type=ServiceType.POWER,
                        provider_asset_ids=("feeder",),
                    ),
                ),
                buffer=BufferSpec(
                    unit="reserve_unit",
                    capacity_units=4,
                    initial_units=4,
                    depletion_units_per_minute=1,
                    recovery_units_per_minute=1,
                ),
            ),
            InfrastructureAsset(
                id="air-scrubber",
                name="Deep-sector air scrubber",
                kind=AssetKind.FACILITY,
                provides=ServiceType.AIR,
                dependency_groups=(
                    DependencyGroup(
                        id="scrubber-power",
                        service_type=ServiceType.POWER,
                        provider_asset_ids=("feeder", "scrubber-battery"),
                    ),
                    DependencyGroup(
                        id="scrubber-water",
                        service_type=ServiceType.WATER,
                        provider_asset_ids=("deep-pump",),
                    ),
                ),
                buffer=no_reserve,
            ),
            InfrastructureAsset(
                id="clinic",
                name="Deep-sector clinic",
                kind=AssetKind.DEMAND_ENDPOINT,
                provides=ServiceType.MEDICAL,
                dependency_groups=(
                    DependencyGroup(
                        id="clinic-power",
                        service_type=ServiceType.POWER,
                        provider_asset_ids=("feeder",),
                    ),
                    DependencyGroup(
                        id="clinic-air",
                        service_type=ServiceType.AIR,
                        provider_asset_ids=("air-scrubber",),
                    ),
                ),
                buffer=BufferSpec(
                    unit="reserve_unit",
                    capacity_units=3,
                    initial_units=3,
                    depletion_units_per_minute=1,
                    recovery_units_per_minute=1,
                ),
            ),
        ),
        demands=(
            Demand(
                id="shelter-air",
                community_id="deep-shelter",
                served_by_asset_id="air-scrubber",
                service_type=ServiceType.AIR,
                population=shelter_population,
                priority_weight=shelter_weight,
            ),
            Demand(
                id="clinic-medical",
                community_id="clinic-district",
                served_by_asset_id="clinic",
                service_type=ServiceType.MEDICAL,
                population=clinic_population,
                priority_weight=clinic_weight,
            ),
        ),
        faults=(
            FaultEvent(
                id="geothermal-feeder-outage",
                asset_id="feeder",
                start_minute=0,
            ),
        ),
        resources=(
            InterventionResource(
                id="mobile-generator",
                name="Mobile generator",
                capabilities=(ServiceType.POWER,),
                travel_times=tuple(
                    TravelTime(
                        asset_id=asset_id,
                        travel_minutes=0,
                        setup_minutes=0,
                    )
                    for asset_id in (
                        "deep-pump",
                        "scrubber-battery",
                        "air-scrubber",
                        "clinic",
                    )
                ),
            ),
        ),
    )
