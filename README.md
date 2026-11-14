# LIFELINE

LIFELINE is a deterministic decision-support prototype for exploring cascading infrastructure failures. It combines a functional dependency simulator, an exhaustive small-instance intervention optimizer, comparable baselines, and independently replayable Decision Receipts.

The Milestone 4 web demo connects directly to the Python engine. It does not calculate infrastructure outcomes in the browser or describe weighted service-person-minutes as lives saved.

## Run the interactive demo

The repository is intended to live at `/Volumes/XcodeSSD/Hollow-Hackathon`. Mount `XcodeSSD` before launching it. Frontend packages, Python bytecode, pip/npm caches, logs, and temporary files are kept on that external volume.

```sh
cd /Volumes/XcodeSSD/Hollow-Hackathon/frontend
npm ci --cache /Volumes/XcodeSSD/Hollow-DevData/caches/npm
npm run dev
```

Open the local Vite URL printed in the terminal (normally `http://127.0.0.1:5173`). One command starts the Python API on `127.0.0.1:8000` and the frontend. The development launcher checks that the repository and `Hollow-DevData` exist on the mounted external volume before starting; it does not fall back to an internal path.

The API uses the existing environment at `backend/.venv`. To run it directly:

```sh
cd /Volumes/XcodeSSD/Hollow-Hackathon/backend
PYTHONPYCACHEPREFIX=/Volumes/XcodeSSD/Hollow-DevData/caches/python-pycache \
PIP_CACHE_DIR=/Volumes/XcodeSSD/Hollow-DevData/caches/pip \
TMPDIR=/Volumes/XcodeSSD/Hollow-DevData/temp \
.venv/bin/python -m engine.api
```

## Demo flow

1. Select the coupled utility incident and inspect its fault propagation on the dependency map.
2. Scrub or play the minute-by-minute trace, switching among no intervention, static priority, greedy, and exact plans.
3. Disable a response team or change its route time; recalculate to run the same engine on changed inputs.
4. Compare per-demand service outcomes and plan scores.
5. Inspect the receipt and run the backend verifier.

The model is deliberately abstract: binary service, AND dependency groups, OR providers, integer reserve, and deterministic faults/travel. A valid receipt confirms consistency with the versioned model, not physical accuracy or operational suitability.

## Tests

```sh
cd /Volumes/XcodeSSD/Hollow-Hackathon/backend
.venv/bin/python -m unittest discover -s tests -v

cd /Volumes/XcodeSSD/Hollow-Hackathon/frontend
npm test
npm run build
```

See [ARCHITECTURE.md](./ARCHITECTURE.md), [DATA_CONTRACTS.md](./DATA_CONTRACTS.md), and [TESTING.md](./TESTING.md) for model and verification details.
