# LIFELINE agent handoff

## Current milestone

Milestone 1 is limited to validated contracts, the functional dependency model, deterministic one-minute simulation, the hand-calculated scenario, and tests.

## Do not implement without approval

- Optimizer or policy search
- Decision Receipts, hashing, signatures, or replay verification
- Frontend, API server, database, or deployment
- Physical repair actions or resource reuse
- Real-world telemetry, network datasets, or claims of operational validity

## Required invariants

1. Physical faults are exogenous and cannot be undone by a backup-service intervention.
2. Dependency groups are ANDed; providers within a group are ORed.
3. Provider graph must be acyclic; topological order is stable.
4. Events use half-open minute intervals. One-minute service is credited from state at the interval's starting boundary.
5. A buffer supports full binary service while positive; it is asset-specific abstract reserve, not a real-world duration.
6. Metrics are service-person-minutes and explicitly weighted service-person-minutes. Never rename them “lives saved.”
7. Same validated input must produce the same result with no input mutation.

## Verification

Install the declared package from this directory if needed, then run:

```sh
python -m unittest discover -s tests -v
```

Before any follow-on work, inspect `ARCHITECTURE.md`, `DATA_CONTRACTS.md`, and `TESTING.md`; those documents define the current contract and boundary.

## Proposed Milestone 2

After explicit approval, implement a small exact enumerator over one-shot, compatible backup-service assignments. Enumerate idle and each eligible resource-to-dependency-group assignment, simulate each feasible plan through the existing engine, use a declared deterministic objective/tie-break, and report full enumeration counts. Add a tiny independently checkable optimality fixture and compare against no-action and simple greedy baselines. Do not claim general optimality or a latency target beyond the validated finite instance.
