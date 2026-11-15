# LIFELINE

LIFELINE is a deterministic decision-support prototype for exploring cascading infrastructure failures. It combines a functional dependency simulator, an exhaustive small-instance intervention optimizer, comparable baselines, and independently replayable Decision Receipts.

The Milestone 4 web demo connects directly to the Python engine. It does not calculate infrastructure outcomes in the browser or describe weighted service-person-minutes as lives saved.

## Run the interactive demo

Use Python 3.11–3.13 and Node 22 or newer (Vite requires Node 22.12+ on the Node 22 line). From the repository root:

```sh
python3.13 -m venv backend/.venv
backend/.venv/bin/python -m pip install --no-cache-dir -e ./backend
cd frontend
npm ci --cache ../.lifeline/caches/npm
npm run dev
```

Open the local Vite URL printed in the terminal (normally `http://127.0.0.1:5173`). One command starts the Python API on `127.0.0.1:8000` and the frontend. The launcher resolves paths relative to this checkout and stores logs, caches, and temporary files in ignored `.lifeline/`. No external drive is required. Stop both processes with Ctrl-C.

To run the API directly from the repository root:

```sh
cd backend
.venv/bin/python -m engine.api
```

After `npm run build` in `frontend/`, the API also serves the production frontend at `http://127.0.0.1:8000`. This is a loopback-only local demo, not a public deployment configuration.

## Public hosting (Milestone 6)

The Render Blueprint in `render.yaml` builds the existing frontend and serves it with the Python API from one Gunicorn service. Public evaluation and receipt verification use bounded, killable subprocesses; the model and Field Dossier interface are unchanged. Build with `bash scripts/build.sh` and start with `bash scripts/start.sh` in the intended Python environment. The production entry point binds `0.0.0.0:$PORT`; normal `npm run dev` remains loopback-only.

See [DEPLOYMENT.md](./DEPLOYMENT.md) for Render authorization and HTTPS verification, [SECURITY.md](./SECURITY.md) for exact limits, and [API_GUIDE.md](./API_GUIDE.md) for requests and errors. A public URL is not considered deployed until tested.

## Demo flow

1. Select the coupled utility incident and inspect its fault propagation on the dependency map.
2. Scrub or play the minute-by-minute trace, switching among no intervention, static priority, greedy, and exact plans.
3. Disable a response team or change its route time; recalculate to run the same engine on changed inputs.
4. Compare per-demand service outcomes and plan scores.
5. Inspect the receipt and run the backend verifier.

The model is deliberately abstract: binary service, AND dependency groups, OR providers, integer reserve, and deterministic faults/travel. A valid receipt confirms consistency with the versioned model, not physical accuracy or operational suitability.

## Tests

```sh
cd ~/Projects/LIFELINE/backend
.venv/bin/python -m pip install -r requirements-production.txt
.venv/bin/python -m unittest discover -s tests -v

cd ~/Projects/LIFELINE/frontend
npm test
npm run build

cd ..
backend/.venv/bin/python scripts/smoke.py
```

See [ARCHITECTURE.md](./ARCHITECTURE.md), [DATA_CONTRACTS.md](./DATA_CONTRACTS.md), and [TESTING.md](./TESTING.md) for model and verification details.
