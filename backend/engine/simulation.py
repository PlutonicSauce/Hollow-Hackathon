"""Deterministic one-minute functional dependency simulation."""

from __future__ import annotations

from collections import defaultdict

from .models import (
    AssetSnapshot,
    Demand,
    DemandMetric,
    FaultEvent,
    Intervention,
    Scenario,
    SimulationResult,
    TimeStep,
)


def simulate(scenario: Scenario) -> SimulationResult:
    """Run a scenario without mutating its validated input."""
    assets_by_id = {asset.id: asset for asset in scenario.assets}
    faults_by_asset: dict[str, list[FaultEvent]] = defaultdict(list)
    for fault in scenario.faults:
        faults_by_asset[fault.asset_id].append(fault)

    interventions_by_group: dict[
        str, list[tuple[Intervention, int, int]]
    ] = defaultdict(list)
    for intervention in scenario.interventions:
        resource = next(
            item for item in scenario.resources if item.id == intervention.resource_id
        )
        travel_minutes = next(
            route.travel_minutes
            for route in resource.travel_times
            if route.asset_id == intervention.target_asset_id
        )
        setup_minutes = next(
            route.setup_minutes
            for route in resource.travel_times
            if route.asset_id == intervention.target_asset_id
        )
        active_from = (
            intervention.dispatch_minute
            + travel_minutes
            + setup_minutes
        )
        active_until = (
            scenario.horizon_minutes
            if intervention.duration_minutes is None
            else min(
                scenario.horizon_minutes,
                active_from + intervention.duration_minutes,
            )
        )
        interventions_by_group[intervention.dependency_group_id].append(
            (intervention, active_from, active_until)
        )

    reserve = {
        asset.id: asset.buffer.initial_units
        for asset in scenario.assets
    }
    served_minutes = {demand.id: 0 for demand in scenario.demands}
    steps: list[TimeStep] = []
    ordered_asset_ids = scenario.topological_asset_ids()

    for minute in range(scenario.horizon_minutes + 1):
        active_faults = {
            fault.id
            for fault in scenario.faults
            if fault.start_minute <= minute
            and (fault.end_minute is None or minute < fault.end_minute)
        }
        active_intervention_ids: set[str] = set()
        active_intervention_groups: set[str] = set()
        for intervention, active_from, active_until in (
            entry
            for entries in interventions_by_group.values()
            for entry in entries
        ):
            if active_from <= minute < active_until:
                active_intervention_ids.add(intervention.id)
                active_intervention_groups.add(intervention.dependency_group_id)

        service_available: dict[str, bool] = {}
        physically_faulted: dict[str, bool] = {}
        unsatisfied_by_asset: dict[str, tuple[str, ...]] = {}

        for asset_id in ordered_asset_ids:
            asset = assets_by_id[asset_id]
            faulted = any(
                fault.id in active_faults for fault in faults_by_asset[asset_id]
            )
            unsatisfied_groups = tuple(
                group.id
                for group in asset.dependency_groups
                if not (
                    any(service_available[provider_id] for provider_id in group.provider_asset_ids)
                    or group.id in active_intervention_groups
                )
            )
            dependencies_satisfied = not unsatisfied_groups
            service_available[asset_id] = not faulted and (
                dependencies_satisfied or reserve[asset_id] > 0
            )
            physically_faulted[asset_id] = faulted
            unsatisfied_by_asset[asset_id] = unsatisfied_groups

        snapshots = tuple(
            AssetSnapshot(
                asset_id=asset_id,
                service_available=service_available[asset_id],
                physical_fault_active=physically_faulted[asset_id],
                unsatisfied_dependency_group_ids=unsatisfied_by_asset[asset_id],
                buffer_units=reserve[asset_id],
            )
            for asset_id in ordered_asset_ids
        )
        steps.append(
            TimeStep(
                minute=minute,
                assets=snapshots,
                active_fault_ids=tuple(sorted(active_faults)),
                active_intervention_ids=tuple(sorted(active_intervention_ids)),
            )
        )

        if minute == scenario.horizon_minutes:
            break

        for demand in scenario.demands:
            if service_available[demand.served_by_asset_id]:
                served_minutes[demand.id] += 1

        for asset_id in ordered_asset_ids:
            asset = assets_by_id[asset_id]
            if physically_faulted[asset_id]:
                continue
            if not unsatisfied_by_asset[asset_id]:
                reserve[asset_id] = min(
                    asset.buffer.capacity_units,
                    reserve[asset_id] + asset.buffer.recovery_units_per_minute,
                )
            else:
                reserve[asset_id] = max(
                    0,
                    reserve[asset_id] - asset.buffer.depletion_units_per_minute,
                )

    demand_metrics = tuple(
        _demand_metric(demand, served_minutes[demand.id], scenario.horizon_minutes)
        for demand in scenario.demands
    )
    return SimulationResult(
        scenario_id=scenario.id,
        horizon_minutes=scenario.horizon_minutes,
        steps=tuple(steps),
        demand_metrics=demand_metrics,
        total_service_person_minutes=sum(
            metric.service_person_minutes for metric in demand_metrics
        ),
        total_weighted_service_person_minutes=sum(
            metric.weighted_service_person_minutes for metric in demand_metrics
        ),
        total_possible_service_person_minutes=sum(
            metric.total_service_person_minutes for metric in demand_metrics
        ),
    )


def _demand_metric(
    demand: Demand, served_minutes: int, horizon_minutes: int
) -> DemandMetric:
    possible = demand.population * horizon_minutes
    delivered = demand.population * served_minutes
    return DemandMetric(
        demand_id=demand.id,
        community_id=demand.community_id,
        service_type=demand.service_type,
        population=demand.population,
        served_minutes=served_minutes,
        service_person_minutes=delivered,
        total_service_person_minutes=possible,
        coverage_parts_per_million=(delivered * 1_000_000) // possible,
        priority_weight=demand.priority_weight,
        weighted_service_person_minutes=delivered * demand.priority_weight,
    )
