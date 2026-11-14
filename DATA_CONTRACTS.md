# LIFELINE data contracts — Milestone 1

The runtime contracts are Pydantic v2 models in `backend/engine/models.py`. Unknown fields are rejected, models are immutable at the model level, primitive counts are strict integers, and cross-record references are checked by `Scenario`.

## Inputs

| Model | Required fields and rules |
|---|---|
| `Scenario` | `id`, positive `horizon_minutes`, nonempty `assets`; optional `demands`, `faults`, `resources`, `interventions`. IDs are unique within each record type. All references and graph constraints are validated. |
| `InfrastructureAsset` | `id`, `name`, `kind`, one `provides: ServiceType`, zero or more dependency groups, and a `BufferSpec`. A `source` cannot have dependency groups. |
| `DependencyGroup` | Globally unique `id`, `service_type`, and one or more distinct `provider_asset_ids`. Providers must exist and provide the matching service. |
| `BufferSpec` | Nonempty asset-specific `unit`, integer `capacity_units`, `initial_units`, `depletion_units_per_minute`, and `recovery_units_per_minute`. Initial reserve must be at most capacity; all counts are nonnegative. |
| `FaultEvent` | Unique `id`, known `asset_id`, nonnegative `start_minute`, optional `end_minute` strictly greater than start. Faults are binary and active on a half-open interval. |
| `Demand` | Unique `id`, `community_id`, known `served_by_asset_id`, matching `service_type`, positive `population`, positive `priority_weight`. Different service demands may refer to the same community/population. |
| `InterventionResource` | Unique `id`, one or more distinct service `capabilities`, and unique `TravelTime` records containing nonnegative travel minutes for known assets. |
| `TravelTime` | `asset_id` and nonnegative integer `minutes`; each asset appears at most once per resource. |
| `Intervention` | Unique `id`, known resource, target asset and dependency group, nonnegative dispatch/setup times, optional positive duration. Resource capability must match the group; route must exist; resource can have only one intervention; support must begin before the horizon. |

`ServiceType` is one of `power`, `water`, `air`, `medical`, or `transit`. `AssetKind` is one of `source`, `facility`, or `demand_endpoint`.

### Intervention boundary

The only intervention effect in this milestone is a temporary backup provider for a single named dependency group on a target asset. It cannot change a physical fault, alter another group's service, or increase a provider's capacity. This makes a portable generator-to-power-input example representable without pretending it repairs a broken pump or feeder.

## Outputs

| Model | Meaning |
|---|---|
| `AssetSnapshot` | Asset service availability, active physical-fault flag, unsatisfied group IDs, and reserve units at one boundary. |
| `TimeStep` | State at a boundary minute, sorted active fault/intervention IDs, and all asset snapshots. A run contains `horizon_minutes + 1` steps. |
| `DemandMetric` | Per-demand served interval count, service-person-minutes, total possible service-person-minutes, integer coverage in parts per million, and weighted service-person-minutes. |
| `SimulationResult` | Scenario/horizon, full deterministic trace, per-demand metrics, and aggregate unweighted/weighted service-person-minutes. |

All time fields are whole minutes. No floating point values are used in inputs or returned metrics.

## Example

```python
from engine.scenarios import hand_calculated_scenario
from engine.simulation import simulate

scenario = hand_calculated_scenario()
result = simulate(scenario)
assert result.demand_metrics[0].service_person_minutes == 20
```

Use the models' JSON validation/serialization methods when exchanging data. Do not rely on unchecked `model_copy(update=...)` for untrusted input; reconstruct or validate the complete updated scenario.
