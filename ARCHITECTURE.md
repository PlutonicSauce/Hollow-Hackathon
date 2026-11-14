# LIFELINE architecture — Milestones 1 and 2

## Purpose and boundary

LIFELINE is a deterministic, tactical **decision-support prototype** for exploring how explicitly modeled service dependencies and finite reserves affect synthetic infrastructure scenarios. Milestones 1 and 2 provide validated contracts, a reproducible functional simulator, and an exhaustive optimizer for small one-shot resource assignment problems. It is not a production emergency-management system, a real-time telemetry platform, or a physical power, water, ventilation, or clinical simulator.

The implementation deliberately models service availability as binary. It does not claim that a graph-only model predicts real hydraulic flows, electrical load, air quality, patient outcomes, or lives saved.

## Project structure

```text
backend/
  engine/
    __init__.py       Public model/simulator interface
    models.py         Pydantic contracts and cross-reference validation
    scenarios.py      Hand-calculable and optimizer demonstration scenarios
    simulation.py     Pure one-minute simulator
    optimizer.py      Exact assignment search and comparable baselines
  tests/
    test_models.py
    test_simulation.py
    test_optimizer.py
  pyproject.toml      Runtime dependency and package metadata
ARCHITECTURE.md
DATA_CONTRACTS.md
TESTING.md
AGENT_HANDOFF.md
```

The simulator has no UI, network, database, or wall-clock dependency. Given the same validated `Scenario`, it returns the same `SimulationResult` without mutating the input. The optimizer measures wall-clock runtime for the exact search, but its decisions depend only on integer scenario values and deterministic plan ordering.

## Functional graph

Each `InfrastructureAsset` produces one named `ServiceType`. Its `DependencyGroup`s encode its service inputs:

- Every group on an asset is required (**AND between groups**).
- A group is satisfied when any listed provider is operational (**OR between providers**).
- A valid temporary intervention may satisfy only its named group, and only for that group's service type.
- A provider must produce the service type named by the group.
- The union of provider-to-dependent edges must be acyclic. The simulator uses a stable topological order; cycles are rejected rather than assigned implicit fixed-point semantics.

There is no flow conservation, capacity sharing, threshold sufficiency, or partial service. A provider either supplies its declared service or it does not.

## State and fault semantics

A **physical fault** is an exogenous event with a half-open interval `[start_minute, end_minute)`. While any physical fault is active on an asset, its output is unavailable regardless of its reserve or incoming backup. The interventions implemented in these milestones do not repair physical faults.

An upstream interruption is different: it makes one or more dependency groups unsatisfied. An asset with at least one reserve unit can continue providing its full service despite unsatisfied groups. Reserve is measured in asset-specific integer units; it is not assumed to be minutes of real-world autonomy.

An intervention is limited to an abstract backup-service effect: a resource with the required capability satisfies one matching dependency group on one target asset after travel and setup. It does not repair a damaged asset, create unrelated service, or override a physical fault on the target. An intervention is active on `[available_minute, end_minute)`, where:

```text
available_minute = dispatch_minute + travel_minutes + setup_minutes
end_minute = min(horizon, available_minute + duration_minutes)
```

If duration is omitted, the support lasts through the scenario horizon. Each resource may be assigned only once per scenario. In optimizer plans, every assignment dispatches at minute 0; a resource may instead remain idle. Assigning multiple resources to the same dependency group is rejected as redundant. A resource can support different groups only when each group has its own distinct assigned resource. The abstract resource has no modeled fuel, capacity, or maintenance state, so support duration and capability should not be mistaken for an operational generator model.

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

## Exact intervention optimization

The optimizer requires at least one explicit demand and an uncommitted scenario. It enumerates one choice for each resource: idle, or any compatible target dependency group with a known route whose travel-plus-setup activation time is before the horizon. For `R` resources with `Aᵢ` eligible actions, the raw candidate count is `product(1 + Aᵢ)`. Any plan assigning more than one resource to a dependency group is infeasible and excluded. Every remaining plan is reconstructed as a validated scenario and evaluated by the same simulator; there are no predefined outcome values or surrogate cascade calculations.

The default maximum is 100,000 raw candidates. Exceeding `max_candidate_plans` raises `OptimizationLimitError` and returns no partial result. Result counts distinguish raw candidates, feasible plans, evaluated plans, and plans eligible for fairness tie-breaking. `exhaustive_search_complete` is true only after all feasible plans are evaluated. The reported `computation_time_ns` measures candidate construction and exact search, excluding baseline evaluations; it is an observation, not a latency guarantee.

### Objective and deterministic tie-breaks

1. Maximize total **weighted service-person-minutes**, the sum over demand records of `population × served_minutes × priority_weight`.
2. Among plans whose primary score is at least `(1 - primary_tolerance_ppm / 1,000,000)` of the best primary score, maximize the minimum coverage across explicit demand records. Each record identifies its community, service type, and need; records are kept separate so one well-served service cannot conceal an unserved different need in that community. Coverage is unweighted service-person-minutes divided by possible service-person-minutes, in parts per million.
3. Minimize total resource travel plus setup minutes.
4. If that cost also ties, minimize the number of assigned interventions, preferring idle resources when deployment does not improve the higher-priority objectives.
5. Break remaining ties by the stable compact-JSON plan identifier.

All comparisons use integers; tolerance is tested by cross multiplication, not floating point. The default tolerance is zero. Weights and tolerance are policy inputs, not calibrated measures of urgency or fairness. This fairness rule protects the least-covered modeled demand record, but cannot express population subgroups or needs missing from the input.

### Baselines

All baselines use the same validated scenario, resources, horizon, event semantics, and simulator as the exact search:

- **No intervention:** all resources remain idle.
- **Static priority:** order compatible actions by direct weighted demand at the target, then travel/setup and stable IDs; assign without reusing a resource or dependency group. It intentionally ignores downstream cascade effects and is a transparent straw baseline, not a claim about a particular emergency operations center.
- **Greedy:** repeatedly simulate every remaining feasible one-action extension, take the largest strictly positive marginal primary-score improvement, and stop when no positive improvement remains. Stable travel/setup and ID ordering resolves ties. This is stronger than static priority but can be suboptimal when actions interact.

Baseline score and minimum-demand-coverage deltas are signed differences from the selected exact plan. Zero or negative improvement is reported as-is; the optimizer does not manufacture an advantage.

## Synthetic optimization demonstration

`signature_scenario()` has a persistent feeder outage, a one-interval pump reserve, a scrubber battery, a clinic reserve, and one mobile generator. The four compatible single assignments plus idle produce five candidate plans. Independently scoring each through the simulator gives:

| Choice | Weighted service-person-minutes |
|---|---:|
| Idle | 720 |
| Generator to deep-pump power | 1,080 |
| Generator to scrubber-battery input | 720 |
| Generator to scrubber power | 720 |
| Generator to clinic power | 920 |

The exact result selects the pump. It provides shelter air for all four intervals (40 people × 4 × weight 3 = 480) and clinic service for three intervals (20 × 3 × weight 10 = 600), totaling 1,080. The best baseline greedy also finds the pump; static priority dispatches directly to the clinic for 920, while no intervention scores 720. Thus the signature demonstrates an upstream-vs-direct-target tradeoff, not an asserted advantage over every baseline. `downstream_priority_scenario()` changes demand weights and independently makes the clinic the best target (40,001 weighted service-person-minutes).

## Remaining model boundaries

The graph has binary service, AND dependency groups, OR providers, and DAG-only propagation. It has no flow conservation, load/capacity sharing, partial service, stochastic failures, repair actions, resource redeployment, fuel consumption, multi-step dispatch, or calibrated physical reserves. Travel/setup are deterministic integer minutes. Community coverage is only as complete as the explicit demand records and weights. Scores are service exposure and policy arithmetic, never lives saved, avoided casualties, or validated operational recommendations.

## Later milestones

Decision Receipts must later include all replay inputs and independently verifiable simulation and optimization steps; a digest alone is not proof of optimality or model validity. UI, deployment, uncertainty modeling, physical repair actions, and real network datasets remain outside these milestones.
