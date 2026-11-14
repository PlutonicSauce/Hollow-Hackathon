# LIFELINE testing — Milestones 1 and 2

## Run

From `backend/`:

```sh
python -m unittest discover -s tests -v
```

The suite uses Python's standard `unittest` runner; the runtime dependency is Pydantic v2. In this workspace, run the project virtual environment with:

```sh
cd backend
.venv/bin/python -m unittest discover -s tests -v
```

## Coverage

- **Contract validation:** invalid reserve ranges and horizon; missing provider/demand/fault/resource/target references; service-type mismatch; duplicate IDs; invalid or beyond-horizon interventions.
- **Graph semantics:** OR among providers, AND among dependency groups, stable topological ordering, and rejection of cycles.
- **Physical fault vs. supply loss:** physical faults suppress service and are not cleared by backup interventions; interrupted inputs consume reserve instead.
- **Reserve boundaries:** reserve sustains service through the interval in which it drains to zero; zero reserve plus missing inputs causes outage; restored inputs recover service and recharge up to capacity.
- **Interventions:** capability and route validation; support starts only after travel/setup; support satisfies only its targeted group; no effect on a physically faulted target.
- **Determinism:** repeated simulations of identical validated inputs return equal results and traces.
- **Hand calculation:** the four-minute synthetic scenario returns 2 served minutes, 20 service-person-minutes from 10 people, 40 possible service-person-minutes, 500,000 coverage ppm, and 40 weighted service-person-minutes.
- **Enumeration:** zero/one/multiple resources, idle choices, incompatible targets, duplicate dependency-group rejection, candidate limits, and exhaustive counts.
- **Objective:** integer tolerance behavior, minimum coverage for each separate community/service/need demand record, travel/setup-cost and action-count tie-breaks, stable plan IDs, and repeat-run determinism.
- **Independent optimization check:** explicitly simulate every compatible single action in `signature_scenario()` and assert scores of 720 (idle), 1,080 (deep pump), 720 (scrubber battery), 720 (scrubber), and 920 (clinic). The optimum is hand-checked as pump service producing 480 weighted shelter service-person-minutes plus 600 weighted clinic service-person-minutes.
- **Arrival boundaries:** travel/setup activation exactly at a reserve-exhaustion boundary prevents the outage; arrival one minute later permits an outage before recovery. Delaying the pump route changes the recommended target.
- **Counterfactuals:** no-action, static-priority, and greedy baselines run through the same simulator; tests cover both upstream-best and downstream-best cases, a greedy trap, fairness trade-offs, and a no-benefit case.
- **Measured runtime:** `OptimizationResult.computation_time_ns` is an observed integer measurement for exact search only. Tests do not impose a latency promise; baseline evaluations are excluded from that field.

## Expected test discipline

Tests assert externally meaningful states and metrics, not private helper details. Any change to event ordering, reserve boundary behavior, optimization semantics, or metric units must update the architecture/data-contract documentation and hand-calculated expectations. A passing synthetic suite is evidence of contract conformance, not physical validity or operational readiness.
