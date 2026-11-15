# LIFELINE architecture — Milestones 1–3

## Purpose and boundary

LIFELINE is a deterministic, tactical **decision-support prototype** for exploring how explicitly modeled service dependencies and finite reserves affect synthetic infrastructure scenarios. Milestones 1–3 provide validated contracts, a reproducible functional simulator, an exhaustive optimizer for small one-shot resource assignment problems, and Decision Receipts with independent replay and bounded optimality verification. It is not a production emergency-management system, a real-time telemetry platform, or a physical power, water, ventilation, or clinical simulator.

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
    receipts.py       Versioned receipt contracts and canonical SHA-256 payloads
    verification.py   Independent replay, baseline, and exact-space verifier
    receipt_fixtures.py Deterministic receipt fixture generator
  tests/
    test_models.py
    test_simulation.py
    test_optimizer.py
    test_receipts.py
  pyproject.toml      Runtime dependency and package metadata
.github/workflows/tests.yml
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

## Decision Receipts and verification

`DecisionReceipt` contains a versioned payload with the complete uncommitted `Scenario` (including assets, dependencies, fault intervals, initial reserves, demands, routes, resource constraints, and horizon), optimizer policy, recommended assignments, selected state trace, service outcomes, search counts, baseline results, metric definitions, assumptions, and limitations. Model, optimizer, schema, and canonicalization versions are explicit. The deterministic fixture generator is `engine.receipt_fixtures.signature_receipt_fixture()`.

The payload digest is SHA-256 over UTF-8 bytes produced by the versioned **LIFELINE JSON v1** canonicalization: convert Pydantic values in JSON mode, serialize with lexicographically sorted object keys, compact `(",", ":")` separators, `ensure_ascii=False`, and `allow_nan=False`. Receipt models and scenario contracts use integer-valued metrics; floats are not accepted as replay inputs. The outer integrity record and optional execution metadata are not hashed. Exact-search duration and verification duration are observational metadata, not decision inputs.

The verifier checks receipt structure and supported versions, reconstructs the strict `Scenario`, validates intervention constraints, recomputes the payload digest, replays the recommended plan with the declared simulator, and independently derives demand/objective metrics from the resulting state trace. It separately reconstructs each baseline and independently enumerates compatible one-shot assignments, recomputes the best primary score and fairness-eligible set, checks deterministic tie-breaking, and compares counts and selected plan. It does **not** call `optimize_interventions()`; the verifier uses a separately structured candidate model and enumerator.

The verifier deliberately shares the versioned `simulate()` state-transition implementation with the optimizer. A passing replay therefore establishes internal consistency with that simulator, not physical accuracy or independent validation of its rules. Hand-calculated M1 and optimization oracles are retained to detect errors common to both paths. Verification reports distinguish schema, version, digest integrity, input validity, replay/reproducibility, baseline, and optimality failures.

The digest covers every replay-critical payload field, but an ordinary hash is not an authorship signature. It detects changes only relative to a trusted digest. An attacker able to replace both payload and digest can produce a new internally consistent hash; replay and independent enumeration reject unsupported outcome/optimality claims, but cannot prove who created a fully recomputed receipt or whether its scenario describes reality. No signature, external timestamp, or public-key infrastructure is implemented.

## Stronger multi-resource demonstration

`coupled_utility_scenario()` models a failed feeder and interrupted aquifer supply feeding one pump that requires both power and water. A generator and water tanker each have limited assignments; the tanker reaches the pump after one minute. The pump serves both a shelter scrubber and community water distribution. A finite scrubber battery preserves air service during the short planning horizon.

There are eight candidate plans, all eight feasible and evaluated. The exact plan assigns the generator to `pump-power` and the tanker to `pump-source-water`; pump service resumes at minute 1. Its score is 1,100 weighted service-person-minutes: 40 shelter occupants × 5 served minutes × weight 3 = 600, plus 50 water recipients × 5 × weight 2 = 500. No intervention scores 0; static direct-priority and one-step greedy each score 720 by assigning the tanker directly to the scrubber water input. Neither baseline combines the two individually non-beneficial pump-input assignments. This is a finite-resource complementarity case, not evidence that exact search always beats greedy. The signature case still ties greedy, and the fairness fixture separately shows a configured aggregate-score tradeoff.

The fairness result is a policy choice, not an ethically objective answer. In the two-community fixture, best primary score is 200; with a human-selected 400,000 ppm relative tolerance, the result selects 120 primary points and improves worst-demand coverage from 0 to 500,000 ppm. Stakeholders must choose the tolerance and weights; neither is calibrated as a universal ethical rule.

## Remaining model boundaries

The graph has binary service, AND dependency groups, OR providers, and DAG-only propagation. It has no flow conservation, load/capacity sharing, partial service, stochastic failures, repair actions, resource redeployment, fuel consumption, multi-step dispatch, or calibrated physical reserves. Travel/setup are deterministic integer minutes. Community coverage is only as complete as the explicit demand records and weights. Scores are service exposure and policy arithmetic, never lives saved, avoided casualties, or validated operational recommendations.

## Later milestones

The next approved milestone may build a frontend that displays receipt inputs, action assignments, minute-by-minute replay, fairness/score tradeoffs, verification findings, and model limits. It should not imply that a valid receipt proves real-world accuracy or lives saved. Cloud deployment, uncertainty modeling, physical repair actions, and real network datasets remain out of scope until separately approved.

## Milestone 4 interactive application

The local application is a React/TypeScript single-page interface backed by `engine.api`, a standard-library Python HTTP server. The API accepts strict `Scenario` and `OptimizationPolicy` payloads and delegates all simulation, exact enumeration, baseline evaluation, receipt generation, and receipt verification to the existing Python engine. The client owns presentation state only: selected scenario, viewed plan, replay minute, and user-edited scenario inputs.

`POST /api/evaluate` returns the validated scenario, no-intervention simulation, exact optimization result, receipt, and minute traces for no intervention, static priority, greedy, and selected exact plans. Every trace is generated by `simulate()`. `POST /api/verify` sends the exported receipt through `verify_decision_receipt()`. Invalid contracts and bounded-search failures return explicit 4xx JSON errors. The service binds to loopback only.

The dependency map derives its nodes, provider edges, and selected-time service status from the API scenario and trace. Resource checkboxes remove resources from the input scenario; route-time edits change the input route; both require a new API evaluation before changing outcome displays. The fairness control supplies `primary_tolerance_ppm` to the optimizer. Visual bar lengths are normalized display values from API-returned scores and are not alternative model metrics.

The dev launcher starts the API and Vite together, with npm/pip caches, Python bytecode, logs, and temporary files rooted under the checkout's ignored `.lifeline/` directory. Paths are resolved relative to the launcher, and a missing `backend/.venv` produces setup guidance. No external drive is required. VS Code's user-data and Copilot session storage are separate application-level paths and are not redirected by this project launcher.

The first slice is a local synthetic-scenario demo, not an operational service. It has no authentication, persistence of edited scenarios, physical capacity model, live data, cloud deployment, or real-world calibration.

## Milestone 6 public serving

`engine.public_app` is a WSGI boundary served by a single threaded Gunicorn worker. It serves only explicit API routes and built frontend assets on one origin. Public computations are admitted one at a time, rate-limited globally, and executed in disposable subprocesses with CPU, Linux memory, and kill/reap wall-clock limits. Both evaluation scenarios and replay inputs inside receipts undergo the same public size, graph, candidate-space, and combined-work admission checks before engine execution. These are hosting restrictions, not changes to versioned simulation or verification semantics; declared receipt policy and hashed payloads remain intact.

The Render Free Blueprint builds both layers and supplies dynamic port binding behind HTTPS ingress. No persistence, authentication, separate frontend host, or new model capability is added. See `SECURITY.md` for exact limits, `API_GUIDE.md` for HTTP contracts, and `DEPLOYMENT.md` for authorization and live verification. The development launcher remains loopback-only.
