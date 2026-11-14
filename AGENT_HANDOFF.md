# LIFELINE agent handoff

## Current milestone

Milestone 3 implements versioned Decision Receipts, canonical SHA-256 payloads, deterministic receipt fixtures, independent replay/metric/baseline/exhaustive-plan verification, an interacting multi-resource scenario, expanded tests, and a GitHub Actions workflow. Read `ARCHITECTURE.md`, `DATA_CONTRACTS.md`, and `TESTING.md` before changing semantics.

## Do not implement without approval

- Frontend, dashboards, API server, database, or deployment
- Authentication, PDF export, LLM decision support, GIS, or sensor integrations
- Physical repair actions or resource reuse
- Real-world telemetry, network datasets, or claims of operational validity
- Any Milestone 4 work until explicitly approved

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

## Next milestone boundary

Only begin Milestone 4 after explicit approval. The proposed scope is a focused interactive demo that displays the complete scenario, recommended assignments, minute-by-minute replay, baseline comparisons, fairness tradeoffs, receipt digest, verifier statuses, and explicit model limitations. Do not imply lives saved or operational validity. The prior `3091d96` historical Copilot co-author trailer is not to be rewritten; future commits must have only the configured user's author/committer identity and no attribution footer.
