"""Validated input and output contracts for LIFELINE's first two milestones."""

from __future__ import annotations

from collections import defaultdict, deque
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator


NonEmptyString = Annotated[StrictStr, Field(min_length=1)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
PartsPerMillion = Annotated[StrictInt, Field(ge=0, le=1_000_000)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ServiceType(StrEnum):
    POWER = "power"
    WATER = "water"
    AIR = "air"
    MEDICAL = "medical"
    TRANSIT = "transit"


class AssetKind(StrEnum):
    SOURCE = "source"
    FACILITY = "facility"
    DEMAND_ENDPOINT = "demand_endpoint"


class BufferSpec(Contract):
    """Reserve state and rates, all in the asset's declared integer unit."""

    unit: NonEmptyString
    capacity_units: NonNegativeInt
    initial_units: NonNegativeInt
    depletion_units_per_minute: NonNegativeInt
    recovery_units_per_minute: NonNegativeInt

    @model_validator(mode="after")
    def initial_reserve_fits_capacity(self) -> BufferSpec:
        if self.initial_units > self.capacity_units:
            raise ValueError("initial buffer reserve cannot exceed capacity")
        return self


class DependencyGroup(Contract):
    """One required service; any listed provider can satisfy the group."""

    id: NonEmptyString
    service_type: ServiceType
    provider_asset_ids: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def providers_are_unique(self) -> DependencyGroup:
        if len(set(self.provider_asset_ids)) != len(self.provider_asset_ids):
            raise ValueError("provider_asset_ids must not contain duplicates")
        return self


class InfrastructureAsset(Contract):
    id: NonEmptyString
    name: NonEmptyString
    kind: AssetKind
    provides: ServiceType
    dependency_groups: tuple[DependencyGroup, ...] = ()
    buffer: BufferSpec

    @model_validator(mode="after")
    def dependency_groups_are_unique(self) -> InfrastructureAsset:
        ids = [group.id for group in self.dependency_groups]
        if len(ids) != len(set(ids)):
            raise ValueError("dependency group IDs must be unique within an asset")
        if self.kind == AssetKind.SOURCE and self.dependency_groups:
            raise ValueError("source assets cannot have dependency groups")
        return self


class FaultEvent(Contract):
    """An exogenous binary physical fault active over [start_minute, end_minute)."""

    id: NonEmptyString
    asset_id: NonEmptyString
    start_minute: NonNegativeInt
    end_minute: NonNegativeInt | None = None

    @model_validator(mode="after")
    def end_follows_start(self) -> FaultEvent:
        if self.end_minute is not None and self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be greater than start_minute")
        return self


class Demand(Contract):
    id: NonEmptyString
    community_id: NonEmptyString
    served_by_asset_id: NonEmptyString
    service_type: ServiceType
    population: PositiveInt
    priority_weight: PositiveInt = 1


class TravelTime(Contract):
    asset_id: NonEmptyString
    travel_minutes: NonNegativeInt
    setup_minutes: NonNegativeInt = 0


class InterventionResource(Contract):
    """A portable backup resource that can satisfy specified service inputs."""

    id: NonEmptyString
    name: NonEmptyString
    capabilities: tuple[ServiceType, ...] = Field(min_length=1)
    travel_times: tuple[TravelTime, ...]

    @model_validator(mode="after")
    def resource_entries_are_unique(self) -> InterventionResource:
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("resource capabilities must not contain duplicates")
        route_asset_ids = [route.asset_id for route in self.travel_times]
        if len(set(route_asset_ids)) != len(route_asset_ids):
            raise ValueError("resource travel times must not repeat an asset")
        return self


class Intervention(Contract):
    """Backup service applied only to a matching dependency group."""

    id: NonEmptyString
    resource_id: NonEmptyString
    target_asset_id: NonEmptyString
    dependency_group_id: NonEmptyString
    dispatch_minute: NonNegativeInt
    duration_minutes: PositiveInt | None = None


class Scenario(Contract):
    id: NonEmptyString
    horizon_minutes: PositiveInt
    assets: tuple[InfrastructureAsset, ...] = Field(min_length=1)
    demands: tuple[Demand, ...] = ()
    faults: tuple[FaultEvent, ...] = ()
    resources: tuple[InterventionResource, ...] = ()
    interventions: tuple[Intervention, ...] = ()

    @model_validator(mode="after")
    def references_and_graph_are_valid(self) -> Scenario:
        assets_by_id = _unique_by_id(self.assets, "asset")
        demands_by_id = _unique_by_id(self.demands, "demand")
        faults_by_id = _unique_by_id(self.faults, "fault")
        resources_by_id = _unique_by_id(self.resources, "resource")
        interventions_by_id = _unique_by_id(self.interventions, "intervention")
        del demands_by_id, faults_by_id, interventions_by_id

        groups_by_id: dict[str, tuple[InfrastructureAsset, DependencyGroup]] = {}
        for asset in self.assets:
            for group in asset.dependency_groups:
                if group.id in groups_by_id:
                    raise ValueError(f"duplicate dependency group ID: {group.id}")
                groups_by_id[group.id] = (asset, group)

                for provider_id in group.provider_asset_ids:
                    provider = assets_by_id.get(provider_id)
                    if provider is None:
                        raise ValueError(
                            f"dependency group {group.id} references unknown provider "
                            f"{provider_id}"
                        )
                    if provider.provides != group.service_type:
                        raise ValueError(
                            f"provider {provider_id} supplies {provider.provides}, "
                            f"not {group.service_type}"
                        )

        for demand in self.demands:
            asset = assets_by_id.get(demand.served_by_asset_id)
            if asset is None:
                raise ValueError(
                    f"demand {demand.id} references unknown asset "
                    f"{demand.served_by_asset_id}"
                )
            if asset.provides != demand.service_type:
                raise ValueError(
                    f"demand {demand.id} requests {demand.service_type}, "
                    f"but {asset.id} provides {asset.provides}"
                )

        for fault in self.faults:
            if fault.asset_id not in assets_by_id:
                raise ValueError(
                    f"fault {fault.id} references unknown asset {fault.asset_id}"
                )
            if fault.start_minute >= self.horizon_minutes:
                raise ValueError(
                    f"fault {fault.id} starts at or after the scenario horizon"
                )

        for resource in self.resources:
            route_asset_ids = {route.asset_id for route in resource.travel_times}
            unknown_routes = route_asset_ids - set(assets_by_id)
            if unknown_routes:
                raise ValueError(
                    f"resource {resource.id} has routes to unknown assets: "
                    f"{sorted(unknown_routes)}"
                )

        seen_resource_assignments: set[str] = set()
        seen_intervention_groups: set[str] = set()
        for intervention in self.interventions:
            resource = resources_by_id.get(intervention.resource_id)
            if resource is None:
                raise ValueError(
                    f"intervention {intervention.id} references unknown resource "
                    f"{intervention.resource_id}"
                )
            if intervention.resource_id in seen_resource_assignments:
                raise ValueError(
                    f"resource {intervention.resource_id} has more than one "
                    "intervention in a scenario"
                )
            seen_resource_assignments.add(intervention.resource_id)
            if intervention.dependency_group_id in seen_intervention_groups:
                raise ValueError(
                    f"dependency group {intervention.dependency_group_id} has "
                    "multiple interventions"
                )
            seen_intervention_groups.add(intervention.dependency_group_id)

            target = assets_by_id.get(intervention.target_asset_id)
            if target is None:
                raise ValueError(
                    f"intervention {intervention.id} references unknown target "
                    f"{intervention.target_asset_id}"
                )
            target_group = groups_by_id.get(intervention.dependency_group_id)
            if target_group is None or target_group[0].id != target.id:
                raise ValueError(
                    f"intervention {intervention.id} must target a dependency group "
                    f"belonging to {target.id}"
                )
            if target_group[1].service_type not in resource.capabilities:
                raise ValueError(
                    f"resource {resource.id} cannot provide "
                    f"{target_group[1].service_type}"
                )
            travel_time = next(
                (
                    route
                    for route in resource.travel_times
                    if route.asset_id == target.id
                ),
                None,
            )
            if travel_time is None:
                raise ValueError(
                    f"resource {resource.id} has no travel time to {target.id}"
                )
            if intervention.dispatch_minute >= self.horizon_minutes:
                raise ValueError(
                    f"intervention {intervention.id} dispatches at or after the horizon"
                )
            active_from = (
                intervention.dispatch_minute
                + travel_time.travel_minutes
                + travel_time.setup_minutes
            )
            if active_from >= self.horizon_minutes:
                raise ValueError(
                    f"intervention {intervention.id} becomes available at or after "
                    "the horizon"
                )

        self.topological_asset_ids()
        return self

    def topological_asset_ids(self) -> tuple[str, ...]:
        """Return a stable provider-before-dependent order; reject dependency cycles."""
        outgoing: dict[str, set[str]] = defaultdict(set)
        indegree = {asset.id: 0 for asset in self.assets}

        for asset in self.assets:
            for group in asset.dependency_groups:
                for provider_id in group.provider_asset_ids:
                    if asset.id not in outgoing[provider_id]:
                        outgoing[provider_id].add(asset.id)
                        indegree[asset.id] += 1

        ready = deque(sorted(asset_id for asset_id, degree in indegree.items() if degree == 0))
        ordered: list[str] = []
        while ready:
            asset_id = ready.popleft()
            ordered.append(asset_id)
            for dependent_id in sorted(outgoing[asset_id]):
                indegree[dependent_id] -= 1
                if indegree[dependent_id] == 0:
                    ready.append(dependent_id)

        if len(ordered) != len(indegree):
            raise ValueError("dependency graph must be acyclic")
        return tuple(ordered)


class AssetSnapshot(Contract):
    asset_id: NonEmptyString
    service_available: bool
    physical_fault_active: bool
    unsatisfied_dependency_group_ids: tuple[NonEmptyString, ...]
    buffer_units: NonNegativeInt


class TimeStep(Contract):
    """State at the beginning of a minute; the final step is the horizon boundary."""

    minute: NonNegativeInt
    assets: tuple[AssetSnapshot, ...]
    active_fault_ids: tuple[NonEmptyString, ...]
    active_intervention_ids: tuple[NonEmptyString, ...]


class DemandMetric(Contract):
    demand_id: NonEmptyString
    community_id: NonEmptyString
    service_type: ServiceType
    population: PositiveInt
    served_minutes: NonNegativeInt
    service_person_minutes: NonNegativeInt
    total_service_person_minutes: PositiveInt
    coverage_parts_per_million: PartsPerMillion
    priority_weight: PositiveInt
    weighted_service_person_minutes: NonNegativeInt


class SimulationResult(Contract):
    scenario_id: NonEmptyString
    horizon_minutes: PositiveInt
    steps: tuple[TimeStep, ...]
    demand_metrics: tuple[DemandMetric, ...]
    total_service_person_minutes: NonNegativeInt
    total_weighted_service_person_minutes: NonNegativeInt
    total_possible_service_person_minutes: NonNegativeInt


class PolicyName(StrEnum):
    NO_INTERVENTION = "no_intervention"
    STATIC_PRIORITY = "static_priority"
    GREEDY = "greedy"


class OptimizationPolicy(Contract):
    """Exact optimizer policy parameters; tolerance is a relative primary-score loss."""

    primary_tolerance_ppm: PartsPerMillion = 0
    max_candidate_plans: PositiveInt = 100_000


class CommunityServiceCoverage(Contract):
    demand_id: NonEmptyString
    community_id: NonEmptyString
    service_type: ServiceType
    weighted_service_person_minutes: NonNegativeInt
    total_weighted_service_person_minutes: PositiveInt
    coverage_parts_per_million: PartsPerMillion


class ObjectiveValue(Contract):
    weighted_service_person_minutes: NonNegativeInt
    minimum_community_service_coverage_ppm: PartsPerMillion
    deployment_minutes: NonNegativeInt
    intervention_count: NonNegativeInt


class PlanSummary(Contract):
    plan_id: NonEmptyString
    interventions: tuple[Intervention, ...]
    idle_resource_ids: tuple[NonEmptyString, ...]
    objective: ObjectiveValue
    demand_metrics: tuple[DemandMetric, ...]
    community_service_coverages: tuple[CommunityServiceCoverage, ...]


class BaselineComparison(Contract):
    baseline: PolicyName
    plan: PlanSummary
    primary_score_delta: StrictInt
    minimum_community_service_coverage_delta_ppm: StrictInt


class OptimizationResult(Contract):
    policy: OptimizationPolicy
    candidate_plans: PositiveInt
    feasible_plans: PositiveInt
    plans_evaluated: PositiveInt
    fairness_eligible_plans: PositiveInt
    exhaustive_search_complete: bool
    best_primary_score: NonNegativeInt
    selected_plan: PlanSummary
    baseline_comparisons: tuple[BaselineComparison, ...]
    computation_time_ns: NonNegativeInt


def _unique_by_id(items: tuple[Contract, ...], label: str) -> dict[str, Contract]:
    result: dict[str, Contract] = {}
    for item in items:
        item_id = getattr(item, "id")
        if item_id in result:
            raise ValueError(f"duplicate {label} ID: {item_id}")
        result[item_id] = item
    return result
