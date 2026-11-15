# LIFELINE agent handoff

## Current release

The deployed light React/TypeScript application uses a single Gunicorn service and bounded Python computations. `engine.api` is the loopback-only development server. The API returns real simulation traces, exact optimization/baseline results, Decision Receipts, and verifier reports. Read `README.md`, `ARCHITECTURE.md`, `DATA_CONTRACTS.md`, and `TESTING.md` before changing semantics.

## Scope boundary

The public deployment and light-interface redesign are complete. Preserve the current recovery workspace and security boundary. Do not start a later milestone or add authentication, PDF export, LLM decision support, GIS, sensor integrations, physical repair actions, resource reuse, real-world telemetry, network datasets, or operational claims without approval.

## Required invariants

1. Physical faults are exogenous and cannot be undone by a backup-service intervention.
2. Dependency groups are ANDed; providers within a group are ORed.
3. Provider graph must be acyclic; topological order is stable.
4. Events use half-open minute intervals. One-minute service is credited from state at the interval's starting boundary.
5. A buffer supports full binary service while positive; it is asset-specific abstract reserve, not a real-world duration.
6. Metrics are service-person-minutes and explicitly weighted service-person-minutes. Never rename them “lives saved.”
7. Interventions provide only one matching dependency group; they never repair physical faults. Optimizer assignments dispatch at minute 0, each resource is used at most once, and duplicate target groups are rejected.
8. Exact search must enumerate its entire bounded feasible space or fail explicitly; never return a partial result as optimal.
9. Fairness uses the minimum normalized coverage of explicit demand records, keyed by community, service type, and demand/need. It cannot represent omitted needs or population subgroups.
10. Same validated input must produce the same simulation and plan choice. Computation time is observational and is not part of tie-breaking.
11. A receipt payload includes the complete replay scenario, plan, selected trace, policy, counts, baselines, definitions, assumptions, and limitations. Digest and execution timing are outside the hashed payload.
12. The verifier must not call `optimize_interventions()`. It may call the declared simulator, but must derive metrics from the trace and separately enumerate plans and baselines.
13. A passing verifier establishes consistency with the versioned model, not physical accuracy, authorship, or truth about the real world. SHA-256 alone is not a signature.
14. Future commits use only the configured user identity; do not add AI co-author or attribution trailers, and do not rewrite previous commits to alter attribution.

## Verification

From `backend/`, run:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The GitHub workflow runs `python -m unittest discover -s tests -v` on Python 3.11–3.13 without secrets.

## Milestone 3 evidence

- The signature receipt verifies with all checks passing and retains its deterministic fixture generator in `backend/engine/receipt_fixtures.py`.
- The coupled utility scenario exhaustively evaluates 8 plans. Coordinated generator and tanker assignments restore the shared pump after one minute and score 1,100 weighted service-person-minutes; no action scores 0, static priority 720, and greedy 720.
- The fairness fixture has a 200-point primary optimum. A configured 400,000 ppm tolerance selects 120 points and raises minimum explicit-demand coverage to 500,000 ppm. This is a declared policy tradeoff, not an ethical conclusion.
- Hand-calculated trace expectations remain the oracle for the shared simulator. The verifier separately derives outcomes from its replay trace and independently enumerates the bounded plan space.

## Milestone 4 invariants

- The browser is a presentation/input layer; all service outcomes, plan scores, baselines, traces, receipts, and verification reports come from the Python engine.
- User-edited resource availability and travel times are sent through `Scenario.model_validate` before evaluation.
- The displayed weighted objective is never called lives saved.
- The local API binds to 127.0.0.1. Do not expose it publicly; use the existing bounded production boundary.
- The project dev launcher resolves this checkout and stores cache/temp/log files in ignored `.lifeline/`. It requires `backend/.venv`; no external drive is needed.
- Copilot session history and VS Code user-data are controlled by the active editor launch configuration, not by the LIFELINE dev launcher. Verify those separately; this environment may still keep session state internally.

## Milestone 5: The Field Dossier Redesign

Historical, superseded by the light-interface and recovery-workspace passes; the test counts below describe that earlier milestone only.

Milestone 5 implements the approved creative direction reset to **The Field Dossier**:
- **Design System:** Engineered IBM Plex Sans and IBM Plex Mono typography, warm coal (`#0f0e0c`), amber (`#c8a86b`), sage (`#8aab78`), and clay-red (`#c26b5e`) palette. No gradients, glowing decorative dots, or generic SaaS card borders.
- **Information Architecture:** Incident header with plain-language fault statement and metadata; central System topology graph on the left; sticky Coordinated Response panel on the right with crew dispatches, dynamic complementarity explanation, and immediately visible 4-plan comparison bars (0 vs 720 vs 720 vs 1,100 wSPM).
- **Mobile First-Screen Flow:** The recommended plan, crew dispatches, and comparison bars elevate above the topology map on small viewports so the core decision is understood immediately.
- **Graph Differentiation:** Structural roles for Source infrastructure, Shared Hubs, and Community Demand Endpoints (concentric status rings and truthful dashed backup edges).
- **Truthful Complementarity:** Accurately explains that the pump requires both power and water. Direct response preserves ventilation (720 wSPM), whereas coordinating both crews restores the shared pump, protecting both ventilation and community water (1,100 wSPM). No hardcoded outcomes or false claims.
- **Decision Receipt:** Clean digest row with one-click verification returning 7 explicit check statuses, collapsible payload inspection, and expandable model assumptions/limitations.
- **Verification:** All 60 Python backend tests pass. All 8 frontend Vitest tests pass. TypeScript builds without errors.

## Milestone 6: public serving boundary

Public serving uses `scripts/build.sh`, `scripts/start.sh`, `render.yaml`, and `engine.public_app` under Gunicorn. The loopback-only `engine.api` remains available for development. The Field Dossier UI and versioned simulation/optimization/receipt semantics are preserved. Public admission is defined in `engine.public_limits`; evaluation and verification run in OS-limited subprocesses with a kill/reap deadline. Read `SECURITY.md`, `API_GUIDE.md`, and `DEPLOYMENT.md` before changing hosting limits or worker counts.

CI now checks production HTTP integration and Linux memory limits in addition to the engine/UI tests. A configured Blueprint and passing local checks do not establish a public deployment: account authorization and live HTTPS/browser verification are required. Never claim an untested URL is live.

## Next milestone boundary

Milestone 6 permits the single free Render public demo, its security limits, and deployment validation. Do not add authentication, external data, paid infrastructure, operational claims, or unrelated product areas without approval. The prior `3091d96` historical Copilot co-author trailer is not to be rewritten; future commits must have only the configured user's author/committer identity and no attribution footer.

## Launch frontend redesign

The current UI uses a light-first infrastructure workspace, visible plan radio choices, linked asset inspection and community/timeline status, then response details and Decision Receipt audit. Draft edits require native modal confirmation and do not alter the displayed evaluated run. Preserve the distinction between per-minute availability and whole-horizon coverage. `DESIGN_REVIEW.md` records the design resources, interaction invariants, validation and limitations. Backend semantics and deployment limits are unchanged.

The rejected graphite direction has been replaced with light surfaces, circular service markers, one recommendation, on-demand comparisons and native CSS/SVG motion. Graph motion is tied to real trace states and honors reduced-motion preferences. The map is explicitly schematic. See the current `DESIGN_REVIEW.md`; do not restore the dark layout.

## Final release readiness pass

The release keeps the light recovery workspace, algorithms, receipt semantics and hosting architecture. README and public API/security/deployment/architecture/testing documentation describe the current system. `scripts/release_check.py` validates all five scenarios over Gunicorn HTTP, trace-derived metrics, reproducibility, altered routes and forged/rehashed receipts; it respects the production rate budget. Non-JSON proxy errors are sanitized, and failed receipt verification retries verification rather than optimization. Input edits invalidate pending and completed verification. Historical receipts remain valid for their recorded inputs; do not invent server-side revocation/freshness semantics. Follow TESTING.md for the final suite and live checks. Do not automatically begin another milestone.
