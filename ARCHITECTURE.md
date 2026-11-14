# LIFELINE architecture — Milestone 1

## Purpose and boundary

LIFELINE is a deterministic, tactical **decision-support prototype** for exploring how explicitly modeled service dependencies and finite reserves affect synthetic infrastructure scenarios. Milestone 1 establishes validated contracts and a reproducible functional simulator. It is not a production emergency-management system, a real-time telemetry platform, or a physical power, water, ventilation, or clinical simulator.

The implementation deliberately models service availability as binary. It does not claim that a graph-only model predicts real hydraulic flows, electrical load, air quality, patient outcomes, or lives saved.

## Project structure

```text
backend/
  engine/
    __init__.py       Public model/simulator interface
    models.py         Pydantic contracts and cross-reference validation
    scenarios.py      Small hand-calculable synthetic scenario
    simulation.py     Pure one-minute simulator
  tests/
    test_models.py
    test_simulation.py
  pyproject.toml      Runtime dependency and package metadata
ARCHITECTURE.md
DATA_CONTRACTS.md
TESTING.md
AGENT_HANDOFF.md
```

The simulator has no UI, network, database, optimizer, or wall-clock dependency. Given the same validated `Scenario`, it returns the same `SimulationResult` without mutating the input.

## Functional graph

Each `InfrastructureAsset` produces one named `ServiceType`. Its `DependencyGroup`s encode its service inputs:

- Every group on an asset is required (**AND between groups**).
- A group is satisfied when any listed provider is operational (**OR between providers**).
- A valid temporary intervention may satisfy only its named group, and only for that group's service type.
- A provider must produce the service type named by the group.
- The union of provider-to-dependent edges must be acyclic. The simulator uses a stable topological order; cycles are rejected rather than assigned implicit fixed-point semantics.

There is no flow conservation, capacity sharing, threshold sufficiency, or partial service. A provider either supplies its declared service or it does not.

## State and fault semantics

A **physical fault** is an exogenous event with a half-open interval `[start_minute, end_minute)`. While any physical fault is active on an asset, its output is unavailable regardless of its reserve or incoming backup. It is not repaired by an intervention in Milestone 1.

An upstream interruption is different: it makes one or more dependency groups unsatisfied. An asset with at least one reserve unit can continue providing its full service despite unsatisfied groups. Reserve is measured in asset-specific integer units; it is not assumed to be minutes of real-world autonomy.

An intervention is limited to a physically plausible backup-service effect: a resource with the required capability satisfies one matching dependency group on one target asset after travel and setup. It does not repair a damaged asset, create unrelated service, or override a physical fault on the target. An intervention is active on `[available_minute, end_minute)`, where:

```text
available_minute = dispatch_minute + travel_minutes + setup_minutes
end_minute = min(horizon, available_minute + duration_minutes)
```

If duration is omitted, the support lasts through the scenario horizon. Each resource may be assigned only once per scenario.

## Deterministic one-minute semantics

For each boundary minute `t = 0 ... horizon`:

1. Determine active physical faults and active interventions using the half-open intervals above. Coincident start/end events are resolved by interval membership; no iteration-order race is possible.
2. Visit assets in stable provider-before-dependent topological order.
3. For each dependency group, test whether any provider is operational or its matching intervention is active.
4. An asset is operational iff it is not physically faulted and either all groups are satisfied or its reserve is greater than zero. A source with no dependency groups is operational unless physically faulted.
5. Record an immutable snapshot at boundary `t`.
6. If `t < horizon`, count service over `[t, t+1)` using the recorded operational state, then update reserves:
   - A physically faulted asset's reserve is unchanged.
   - If all dependency groups are satisfied, reserve increases by its recovery rate, capped at capacity.
   - Otherwise, reserve decreases by its depletion rate, floored at zero.

Consequences of this convention: a reserve of one unit can sustain one interval even if it is fully depleted at the end of that interval. If upstream service returns at a boundary with zero reserve, the asset is operational during the next interval and may recharge. A physical fault always suppresses output, even if a backup satisfies all dependency groups.

## Metrics

For demand `d`, with population `P`, horizon `H`, and `S` intervals in which its serving asset is operational:

```text
total_service_person_minutes = P × H
service_person_minutes       = P × S
coverage_ppm                 = floor(service_person_minutes × 1,000,000
                                     / total_service_person_minutes)
weighted_service_person_minutes = service_person_minutes × priority_weight
```

The total metrics sum over demand records. A person included in multiple service demands contributes once per service; this is intentionally a **service exposure** measure, not a count of distinct people or lives saved. Priority weights are scenario policy inputs, not empirically calibrated values.

## Later milestones

Milestone 2 may add a small exact enumerator over the approved intervention semantics. It must compare plans by replaying the same simulator and state its instance-size limits. Later receipt work must include all replay inputs and independent verification; a digest alone is not proof of optimality or model validity. UI, deployment, uncertainty modeling, physical repair actions, and real network datasets remain out of Milestone 1.
