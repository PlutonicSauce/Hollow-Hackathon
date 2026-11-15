# LIFELINE data contracts

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
| `InterventionResource` | Unique `id`, one or more distinct service `capabilities`, and unique `TravelTime` records for known target assets. |
| `TravelTime` | `asset_id`, nonnegative integer `travel_minutes`, and nonnegative integer `setup_minutes` (default zero); each asset appears at most once per resource. |
| `Intervention` | Unique `id`, known resource, target asset and dependency group, nonnegative `dispatch_minute`, and optional positive duration. Travel/setup times come from that resource's validated route. Resource capability must match the group; route must exist; each resource and dependency group can each have only one intervention; support must begin before the horizon. |
| `OptimizationPolicy` | `primary_tolerance_ppm` in `[0, 1_000_000]` (default zero) and positive `max_candidate_plans` (default 100,000). |

`ServiceType` is one of `power`, `water`, `air`, `medical`, or `transit`. `AssetKind` is one of `source`, `facility`, or `demand_endpoint`.

### Intervention boundary

The only intervention effect is temporary backup service for a single named dependency group on a target asset. It cannot change a physical fault, alter another group's service, or increase a provider's capacity. The optimizer dispatches one-shot assignments at minute 0; a resource can be idle but cannot be redeployed. If duration is omitted, support lasts through the horizon. Multiple resources targeting the same dependency group are rejected as redundant. Travel and setup are deterministic integer minutes, with activation at `dispatch_minute + travel_minutes + setup_minutes`.

## Outputs

| Model | Meaning |
|---|---|
| `AssetSnapshot` | Asset service availability, active physical-fault flag, unsatisfied group IDs, and reserve units at one boundary. |
| `TimeStep` | State at a boundary minute, sorted active fault/intervention IDs, and all asset snapshots. A run contains `horizon_minutes + 1` steps. |
| `DemandMetric` | Per-demand served interval count, service-person-minutes, total possible service-person-minutes, integer coverage in parts per million, and weighted service-person-minutes. |
| `SimulationResult` | Scenario/horizon, full deterministic trace, per-demand metrics, and aggregate unweighted/weighted service-person-minutes. |
| `CommunityServiceCoverage` | Coverage for one explicit demand record, retaining its `demand_id`, community, and service type. Demand records are not aggregated, so a separate need cannot be masked by another service within the same community. |
| `ObjectiveValue` | Weighted service-person-minutes, minimum explicit-demand coverage in ppm, total travel-plus-setup minutes, and assignment count used in the final no-op tie-break. |
| `PlanSummary` | Stable plan ID, assignments, idle resources, objective, per-demand metrics, and explicit community/service coverage records. |
| `BaselineComparison` | Baseline policy, its simulated plan, and signed primary-score and minimum-coverage deltas versus the exact recommendation. |
| `OptimizationResult` | Policy, raw/feasible/evaluated/fairness-eligible plan counts, best primary score, selected plan, baseline comparisons, exhaustive-completion flag, and measured exact-search nanoseconds. Runtime excludes baseline evaluation. |
| `DecisionReceipt` | Versioned payload, SHA-256 integrity record, and optional execution metadata outside the digest. |
| `ReceiptPayload` | Complete scenario JSON, policy and resource constraints, recommended `PlanSummary`, selected `TimeStep` trace, exact-search evidence, baseline comparisons, metric definitions, assumptions, and limitations. |
| `ReceiptSearchSummary` | Raw/feasible/evaluated/fairness-eligible counts, exhaustive flag, best and selected primary scores, primary-score loss, and fairness-tradeoff indicator. |
| `ReceiptIntegrity` | Digest algorithm (`sha256`) and a 64-character lowercase hexadecimal digest of the canonical payload. |
| `ReceiptExecutionMetadata` | Exact-search duration in nanoseconds. It is not part of the canonical payload or digest. |
| `ResourceConstraints` | Dispatch minute, maximum assignments per resource/group, idling and redeployment rules, and support-duration policy. Version 1.0 is one-shot at minute 0, one assignment/resource and/group, idling allowed, no redeployment, support through the horizon. |
| `MetricDefinition` | Stable metric name, unit, formula, and interpretation. The verifier rejects changed definitions. |
| `VerificationReport` | `valid`, per-check statuses, independently computed payload digest, verification duration, and structured issues with category/code/message. |
| `VerificationIssue` | One explicit failure reason categorized as schema, version, integrity, input, replay, baseline, or optimality. |

All time fields are whole minutes. No floating point values are used in inputs or returned metrics. Optimizer scores and tolerance comparisons also use integers. Exhaustive search is capped by `max_candidate_plans`; exceeding the cap raises `OptimizationLimitError` rather than returning an incomplete result labeled exact.

## Decision Receipt canonical form

The envelope is JSON with:

- `payload`: all deterministic replay and decision evidence.
- `integrity`: `{ "algorithm": "sha256", "digest": "<64 lowercase hex characters>" }`.
- `execution_metadata`: optional exact-search duration; excluded from the digest.

Payload version fields are `schema_version`, `canonicalization_version`, `simulation_model_version`, and `optimizer_version`. Version 1 values are `1.0`, `lifeline-json-v1`, `1.0`, and `1.0`, respectively. Unsupported versions are rejected for verification rather than interpreted as the current model.

Canonical payload bytes are UTF-8 JSON created from `ReceiptPayload.model_dump(mode="json")` with lexicographically sorted object keys, no insignificant whitespace (`separators=(",", ":")`), literal Unicode (`ensure_ascii=False`), and non-finite numbers prohibited (`allow_nan=False`). The envelope's digest and execution metadata are not included. Payload values use integer metrics; the versioned format does not claim full RFC 8785 compatibility.

Every reported numerical outcome carries its unit/formula in `metric_definitions`: service-person-minutes, priority-weighted service-person-minutes, ppm coverage, resource-minutes, assignment counts, search plan counts, score deltas/loss, and exact-search nanoseconds. Search completeness and fairness-tradeoff indicators are booleans. Service-person metrics count per demand, not distinct people or lives saved.

The scenario is recorded as a JSON object so an incomplete or malformed scenario can be reported as an input-validation failure separately from envelope-schema failure. The verifier reconstructs it with the strict Pydantic `Scenario` contract before replay. The full selected `TimeStep` trace is included; baseline traces are regenerated during verification.

The verifier report has independent statuses for envelope schema, supported versions, digest integrity, input validity, replay/reproducibility, baseline consistency, and exhaustive optimality. `valid` is true only when every status passes. Unsupported semantic versions are not checked using current code.

The digest covers the entire `payload`; it does not cover `integrity` or `execution_metadata`. A plain SHA-256 digest detects changes only relative to a trusted digest. It does not prove authorship, physical truth, or tamper resistance if an attacker can replace both payload and digest. A fully recomputed alternate scenario can form a valid new receipt; no signing or trusted timestamp service is included.

## Example

```python
from engine.scenarios import hand_calculated_scenario
from engine.simulation import simulate

scenario = hand_calculated_scenario()
result = simulate(scenario)
assert result.demand_metrics[0].service_person_minutes == 20
```

Use the models' JSON validation/serialization methods when exchanging data. Do not rely on unchecked `model_copy(update=...)` for untrusted input; reconstruct or validate the complete updated scenario.

For a reproducible example payload, use `engine.receipt_fixtures.signature_receipt_fixture()` and `engine.receipts.export_receipt_json()`. Verify an exported string or mapping with `engine.verification.verify_decision_receipt()`.

## Milestone 4 local HTTP API

The loopback-only server in `backend/engine/api.py` exposes:

| Route | Request | Response |
|---|---|---|
| `GET /api/health` | none | `{ "status": "ok" }` |
| `GET /api/scenarios` | none | Scenario key, display name, and description catalog |
| `GET /api/scenarios/{key}` | known catalog key | Complete validated `Scenario` JSON |
| `POST /api/evaluate` | `{ "scenario": Scenario, "policy"?: OptimizationPolicy }` | Scenario, no-intervention `SimulationResult`, `OptimizationResult`, `DecisionReceipt`, and plan-keyed `TimeStep[]` replay traces |
| `POST /api/verify` | `{ "receipt": DecisionReceipt }` (or receipt object) | `VerificationReport` from the existing independent verifier |

`/api/evaluate` rejects malformed or invalid scenario/policy data with HTTP 422 and includes bounded-search failures as `search_limit_exceeded`. Malformed JSON is HTTP 400; oversized request bodies are rejected. The API computes no alternate domain metrics: plan scores and demand outcomes are serialized directly from engine outputs, and replay traces come from `simulate()`.

The browser can change available resources by omitting them from the scenario resource tuple, edit integer route travel times, and set the existing fairness tolerance. The updated scenario is validated by the same `Scenario` contract before optimization. No browser-side result is accepted as evidence; receipt verification replays and enumerates through Python.

## Public hosting boundary

The model contracts above describe engine semantics. Hosted requests have stricter payload/graph/work limits for both evaluation and receipt verification; see [SECURITY.md](SECURITY.md) and [API_GUIDE.md](API_GUIDE.md). A run has H+1 boundary snapshots, but only the first H contribute service intervals. The final snapshot may differ when support expires at H. An archived receipt is evidence for its recorded input, not an assertion about later drafts.
