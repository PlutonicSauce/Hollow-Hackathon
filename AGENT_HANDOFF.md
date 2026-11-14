# LIFELINE agent handoff

## Current milestone

Milestone 2 implements validated contracts, the deterministic one-minute simulator, exact bounded one-shot intervention assignment, comparable baseline policies, synthetic scenarios, and automated tests. The four core documents (`ARCHITECTURE.md`, `DATA_CONTRACTS.md`, `TESTING.md`, and this handoff) describe the active contract.

## Do not implement without approval

- Decision Receipts, hashing, signatures, or replay verification
- Frontend, API server, database, or deployment
- Physical repair actions or resource reuse
- Real-world telemetry, network datasets, or claims of operational validity
- Any Milestone 3 work until explicitly approved

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

## Verification

From `backend/`, run:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

## Milestone 2 result

The signature case has five raw and feasible plans, all evaluated exhaustively. Hand-calculated weighted service-person-minute scores are 720 for idle, 1,080 for generator-to-pump power, 720 for scrubber-battery input, 720 for scrubber power, and 920 for clinic power. Exact selects the pump. The no-intervention, static-priority, and greedy scores are 720, 920, and 1,080 respectively. A changed-demand scenario makes clinic support best, so upstream intervention is not hardcoded as universally preferable.

## Next milestone boundary

Do not begin Decision Receipts, frontend, deployment, or further optimization features before explicit approval. A Receipt milestone should specify canonical replay inputs and independent simulator/optimality verification; a hash of a recommendation document alone is insufficient. Review all contract and limitation documents before any approved follow-on.
