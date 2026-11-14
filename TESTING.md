# LIFELINE testing — Milestone 1

## Run

From `backend/`:

```sh
python -m unittest discover -s tests -v
```

The suite uses Python's standard `unittest` runner; the runtime dependency is Pydantic v2.

## Coverage required before Milestone 2

- **Contract validation:** invalid reserve ranges and horizon; missing provider/demand/fault/resource/target references; service-type mismatch; duplicate IDs; invalid or beyond-horizon interventions.
- **Graph semantics:** OR among providers, AND among dependency groups, stable topological ordering, and rejection of cycles.
- **Physical fault vs. supply loss:** physical faults suppress service and are not cleared by backup interventions; interrupted inputs consume reserve instead.
- **Reserve boundaries:** reserve sustains service through the interval in which it drains to zero; zero reserve plus missing inputs causes outage; restored inputs recover service and recharge up to capacity.
- **Interventions:** capability and route validation; support starts only after travel/setup; support satisfies only its targeted group; no effect on a physically faulted target.
- **Determinism:** repeated simulations of identical validated inputs return equal results and traces.
- **Hand calculation:** the four-minute synthetic scenario returns 2 served minutes, 20 service-person-minutes from 10 people, 40 possible service-person-minutes, 500,000 coverage ppm, and 40 weighted service-person-minutes.

## Expected test discipline

Tests assert externally meaningful states and metrics, not private helper details. Any later change to event ordering, reserve boundary behavior, or metric units must update both the architecture/data-contract documentation and the hand-calculated expected trace.
