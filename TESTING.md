# LIFELINE testing — Milestones 1–4

## Run

From `backend/`:

```sh
python -m unittest discover -s tests -v
```

The suite uses Python's standard `unittest` runner. Install the pinned production requirements (Pydantic v2 and Gunicorn) for the complete Milestone 6 checks. In this workspace, run:

```sh
cd backend
.venv/bin/python -m pip install -r requirements-production.txt
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

`.github/workflows/tests.yml` installs the pinned production requirements and backend package, then runs the backend suite on Python 3.11, 3.12, and 3.13. Its frontend job runs `npm ci`, `npm test`, and `npm run build` on Node 22, then starts the real Gunicorn server through `scripts/smoke.py`. It uses no secrets or paid services.

## Milestone 4 application tests

Run the API and UI checks from the local checkout:

```sh
cd ~/Projects/LIFELINE/backend
.venv/bin/python -m unittest discover -s tests -v
cd ../frontend
npm test
npm run build
```

`backend/tests/test_api.py` exercises the real loopback HTTP handlers: catalog/scenario loading, the coupled 1,100-versus-720 outputs, generated receipt verification, route/resource counterfactual changes, malformed/invalid inputs, and candidate-bound errors. `frontend/src/App.test.tsx` covers stale results and receipt gating after edits, recomputation and backend errors, plan switching, bounded-search labeling, valid/invalid verification states, keyboard focus order, and graph bounds at mobile and desktop widths. Browser validation additionally loads the running app against the real API; frontend test mocks are not treated as integration evidence.

## Milestone 6 public boundary

`backend/tests/test_public.py` adds admission checks for evaluation **and receipts**, graph/collection/horizon/integer/JSON limits, policy escalation resistance, combined work, unchanged receipt digest, verifier independence, framing/content types, redacted errors, filesystem denial, shared busy/rate responses, and health during load. Real subprocess tests prove wall-deadline kill/reaping and OS CPU termination. The Linux-only allocation test proves the 256 MiB address-space cap; it is skipped locally on macOS and runs in all three Linux CI backend jobs.

After building the frontend, run `backend/.venv/bin/python scripts/smoke.py` from the repository root. It starts and stops Gunicorn on an ephemeral dynamic port, checks built HTML/JS/CSS and API together, evaluates 1,100 versus 720/720 across eight candidates, verifies all seven receipt checks and the original digest, and checks actual HTTP admission/security behavior. It also proves slow uploads are interrupted, concurrent compute is rejected while health responds, and the shared rate budget is enforced. Its single measured round trip is diagnostic, not a performance guarantee.

Remote mode accepts the actual HTTPS origin as an argument, verifies TLS normally, and skips slow-upload/rate-saturation checks. A browser check against that public URL is also required before claiming deployment success. No automated browser E2E framework was added; the existing React tests and HTTP smoke checks are supplemented by browser validation.

## Expected test discipline

Tests assert externally meaningful states and metrics, not private helper details. Any change to event ordering, reserve boundary behavior, optimization semantics, canonical serialization, or metric units must update the architecture/data-contract documentation and hand-calculated expectations. The verifier intentionally shares the production simulator; manual expected traces and score tables help catch errors common to both optimizer and verifier. A passing synthetic suite is evidence of contract conformance, not physical validity or operational readiness.
