# LIFELINE testing — Milestones 1–3

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
- **Receipt determinism:** repeated signature fixture generation produces identical exported JSON and payload digests; execution timing is proven outside the digest.
- **Receipt reconstruction and replay:** the complete scenario reconstructs through Pydantic, recorded selected trace matches replay, and metrics independently derived from trace states match receipt outcomes.
- **Independent verifier:** tests patch `optimize_interventions()` to fail and confirm receipt verification still succeeds. The verifier separately reconstructs baselines and exhaustively enumerates assignments.
- **Manual verifier oracle:** the hand-calculated four-minute M1 case verifies 20 service-person-minutes, 500,000 ppm, 40 weighted service-person-minutes, scrubber availability `[false, false, true, true, true]`, and pump reserve `[1, 0, 1, 2, 2]`.
- **Tampering:** tests reject a changed payload with the old digest, plus modified-and-rehashed scenario inputs, objectives, fairness metrics, baselines, candidate counts, and a replay-consistent but inferior recommendation.
- **Invalid inputs and versions:** malformed JSON and duplicate keys, missing/incomplete scenarios, impossible allocations, and unsupported schema/canonicalization/model/optimizer versions produce structured failures.
- **Fairness evidence:** an explicit 400,000 ppm tolerance selects a 120-point plan instead of the 200-point primary maximum, improving worst-demand coverage to 500,000 ppm. This verifies policy mechanics, not an ethical judgment.
- **Coupled multi-resource scenario:** eight assignments are exhaustively checked; coordinated generator-plus-water-tanker pump support scores 1,100 versus 720 for static priority and greedy and 0 for no action.

## GitHub Actions

`.github/workflows/tests.yml` installs the backend package with `python -m pip install -e .`, then runs the documented `python -m unittest discover -s tests -v` command from `backend/` on Python 3.11, 3.12, and 3.13 for pushes and pull requests targeting `main`. It uses no secrets or paid services.

## Expected test discipline

Tests assert externally meaningful states and metrics, not private helper details. Any change to event ordering, reserve boundary behavior, optimization semantics, canonical serialization, or metric units must update the architecture/data-contract documentation and hand-calculated expectations. The verifier intentionally shares the production simulator; manual expected traces and score tables help catch errors common to both optimizer and verifier. A passing synthetic suite is evidence of contract conformance, not physical validity or operational readiness.
