# LIFELINE

**See how infrastructure failures cascade. Compare constrained responses. Verify the decision.**

[Open the live demo](https://lifeline-patriot-hackfest.onrender.com/) · [Architecture](ARCHITECTURE.md) · [API](API_GUIDE.md) · [Security limits](SECURITY.md) · [Testing](TESTING.md)

LIFELINE is a working decision-support research prototype built for Patriot HackFest Fall 2026. It models how disrupted power, water and other services propagate through explicit infrastructure dependencies, then evaluates where limited response resources can provide temporary backup. Its React interface presents the incident, a recommended response, minute-by-minute service availability and independently checkable Decision Receipts.

All scenarios are synthetic. This is not an emergency operating system or a physically calibrated infrastructure model.

## Why the dependency model matters

A useful intervention is not always at the most visible outage. A pump may need **both power and water**, while a dependent service may accept power from **either a feeder or a reserve provider**. Supporting only one missing input can produce no immediate benefit, even when coordinated support would restore several services.

LIFELINE makes those relationships explicit:

- **Deterministic simulation:** AND between required input groups, OR between providers, finite reserves and precise event boundaries on a directed acyclic graph. The same validated inputs reproduce the same trace.
- **Exact search for supported small problems:** enumerate feasible one-shot resource assignments, compare no response, static priority and greedy baselines, and report the actual search counts. Exceeding a supported limit returns an error, not a partial answer labeled optimal.
- **Transparent verification:** each Decision Receipt contains inputs, assignments, trace, metrics, baseline results, versions and a canonical SHA-256 payload digest. A separate verifier reconstructs the result and enumerates alternatives without calling the optimizer. It shares the versioned simulator; this is internal consistency verification, not independent physical validation or an authorship signature.

## Reproducible demo

Open **Coupled utility failure** and choose **Watch recovery**.

1. At minute 0, the feeder and aquifer supply are physically faulted; air and community water are unavailable.
2. At minute 1, coordinated generator and water-tanker backup restores the shared pump, then both dependent services. The original source faults remain active: backup is not repair.
3. Compare responses at the same minute. The recommended plan scores **1,100**, versus **720** for both static priority and greedy and **0** for no response, across **eight candidate assignments**.
4. Choose **Check this decision → Verify this decision**. All seven receipt checks should pass.
5. Under **Change response conditions**, set the water tanker's travel time to the pump to **5 minutes**, review and confirm. The backend recomputes a **720-point** response supporting the scrubber instead. The previous receipt is blocked from certifying the edited inputs.

The **53% higher score** is the rounded comparison `(1,100 − 720) / 720`. The score sums **population × served minutes × priority weight** over demand records. It counts service exposure, potentially across several services for the same people; it is not distinct people helped or lives saved. In this six-minute scenario, service is counted over intervals starting at minutes 0–5. Minute 6 is the excluded terminal boundary, when temporary backup ends.

| Built-in scenario | Default recommended score | What it demonstrates |
| --- | ---: | --- |
| Coupled utility failure | 1,100 | Complementary power and water assignments beat one-step greedy |
| Feeder cascade | 1,080 | Upstream pump support; exact search ties greedy |
| Clinic-priority incident | 40,001 | Different demand weights make clinic support preferable |
| Coverage trade-off | 200 | Default aggregate objective; a 40% tolerance selects 120 with better minimum coverage |
| Reserve boundary example | 40 | Hand-checkable AND/OR behavior and reserve depletion; no response resources |

These are model-specific examples, not evidence that exact optimization always outperforms a baseline.

## Run locally

Requirements: Python **3.11–3.13**, Node **22.12+ on the Node 22 line**, and npm. No database, API key or external drive is needed. From a fresh checkout:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-production.txt -e ./backend
cd frontend
npm ci --cache ../.lifeline/caches/npm
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://127.0.0.1:5173`). The launcher starts the Python API on `127.0.0.1:8000` and the frontend; Ctrl-C stops both. Checkout-relative development caches and logs live in ignored `.lifeline/`. The development server is loopback-only and must not be exposed publicly.

To rehearse the production service from the repository root, using the installed Python environment:

```sh
export PATH="$PWD/backend/.venv/bin:$PATH"
bash scripts/build.sh
PORT=8001 bash scripts/start.sh
```

This starts Gunicorn on all interfaces, serving the built frontend and `/api` under one origin. Use a trusted local network; public hosting belongs behind the HTTPS proxy described in [DEPLOYMENT.md](DEPLOYMENT.md).

## Architecture and public execution boundary

```text
React / TypeScript → same-origin HTTP API → bounded admission
                                            ↓
                              disposable Python process
                         simulator · optimizer · receipt verifier
```

The browser owns presentation and draft inputs. Python owns every outcome, plan score and verification result. Public serving uses one Gunicorn worker, a shared compute slot and global request budget. Evaluation and verification receive the same graph, payload and work checks; child processes have real CPU, memory (Linux) and kill/reap wall limits. There is no persistent scenario storage, authentication, database, live telemetry or AI dependency.

The Render configuration is a single Free Web Service. The repository requests deployment after CI; services connected only through a public repository URL may require **Manual Deploy → Deploy latest commit**. Free hosting can sleep, cold-start and reject concurrent work. It is suitable for this public demonstration, not a continuously available operational service. Exact setup, recovery and rollout checks are in [DEPLOYMENT.md](DEPLOYMENT.md).

## Validate the release

From the repository root after setup:

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -v
npm --prefix frontend test
npm --prefix frontend run build
backend/.venv/bin/python scripts/smoke.py
backend/.venv/bin/python scripts/release_check.py
backend/.venv/bin/python scripts/smoke.py https://lifeline-patriot-hackfest.onrender.com
```

The release check starts a local production server, checks all five scenarios against fixed plan/score expectations, derives metrics from HTTP-returned traces, verifies receipts, tests recomputation and tampering, and records timings in ignored `.lifeline/release-readiness.json`. It respects the real shared rate limit and may pause for one minute. Public smoke checks avoid saturation. CI runs Python 3.11/3.12/3.13 tests plus frontend tests, build and production HTTP checks. Real-browser checks supplement the automated suite; see [TESTING.md](TESTING.md).

## Technical limits

Public inputs are deliberately small: **24 assets, 128 provider edges, 60 minutes, four resources and 256 raw candidate assignments**, subject to a combined work budget. Only one computation/upload is admitted at once, with 12 computation requests per minute shared across visitors. Each child has an 8-second wall deadline, 6 seconds of CPU time and a 256 MiB Linux virtual-address cap. See [SECURITY.md](SECURITY.md) for the complete contract and error handling.

The model has binary service, deterministic faults/travel and one-shot backup assignments. It does not model flows, loads, partial capacity, uncertainty, physical repairs, redeployment or fuel. Priority weights and fairness tolerance are human policy choices. A verified historical receipt remains valid for its own recorded scenario; it does not certify a later edited scenario. Do not submit confidential, personal or operational incident data.
