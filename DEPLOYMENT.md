# Deploy LIFELINE on Render Free

## One service

`render.yaml` defines one **free Python Web Service**, branch `main`, region Virginia, health path `/api/health`, with automatic deployment after CI checks pass. Render's Python runtime includes Node/npm, so no separate frontend host, container, database, paid plan, or secret is needed. The frontend uses relative `/api/...` URLs.

Build: `bash scripts/build.sh`. This installs the pinned Python runtime requirements and editable engine package, runs `npm ci` from the lockfile, and builds the React app. Editable installation preserves the engine's checkout-relative frontend path. Start: `bash scripts/start.sh`. This checks for the build and execs Gunicorn with `backend/gunicorn.conf.py`, listening on `0.0.0.0:$PORT` (default 8000). The Blueprint pins Python 3.13.18 and Node 22.23.5; local validation may use another supported patch release.

Render supplies HTTPS/TLS and HTTP redirects. Free services sleep after 15 minutes idle and may take about a minute to wake. The filesystem is ephemeral and free hours/build/bandwidth quotas apply. This is a public hackathon demo, not a continuously available emergency service. Keep the instance on **Free** and review workspace usage/spending settings; do not add paid resources. See [Render Free limits](https://render.com/docs/free), [native runtime tools](https://render.com/docs/native-runtimes), and [Blueprint settings](https://render.com/docs/blueprint-spec).

## Authorize and create

1. Sign in at [Render Dashboard](https://dashboard.render.com/).
2. Choose **New → Blueprint**. Connect GitHub if prompted; authorize access to **only `PlutonicSauce/Hollow-Hackathon`**.
3. Select that repository, branch **main**, and `render.yaml`. Give the Blueprint a name such as `lifeline`.
4. Review the single service `lifeline-patriot-hackfest`, **Free** plan, and the build/start/health settings above. Apply/deploy the Blueprint. No environment secrets are requested.
5. Once Render marks the deployment live, copy the actual HTTPS service URL and run the remote smoke command below. Do not infer the URL from the service name; Render can add a uniqueness suffix.

If GitHub is already connected, only steps 2–5 remain. Account login, GitHub app authorization, and any Terms acceptance belong to the account owner. If the requested service name is unavailable, change only its name in the setup/configuration; keep the Free plan and remaining settings.

## Validate before sharing

```sh
# Run from the checkout, with the actual Render URL:
backend/.venv/bin/python scripts/smoke.py https://YOUR-SERVICE.onrender.com
```

Then open that HTTPS URL in a browser: confirm the Field Dossier loads, the coupled utility scenario shows 1,100 versus 720/720, and **Verify this decision** passes all seven checks. Edit a crew/route, recompute, and confirm the backend changes the recommendation. A working local server or green build is not proof of a successful public deployment.

## Local production rehearsal

```sh
python3.13 -m venv backend/.venv
export PATH="$PWD/backend/.venv/bin:$PATH"
bash scripts/build.sh
python scripts/smoke.py
PORT=8001 bash scripts/start.sh
```

This production entry point listens on all interfaces; use it on a trusted local network or behind the hosting proxy. Normal development remains `cd frontend && npm run dev`, which starts the loopback-only API and Vite. Do not expose the development server publicly. Never increase Gunicorn's worker count without redesigning the process-local shared admission/rate limits.

## Troubleshooting and rollback

- **503 / 429:** wait for the admitted job / shared one-minute budget. Health remains available.
- **422 execution limit:** reduce input size; a child was killed or exceeded its OS allocation. No partial result is returned.
- **Build failure:** inspect Render build logs, confirm pinned runtimes and root-level build command; the previous successful deployment remains active.
- **Missing frontend:** use the build script from repository root, then restart. The start script fails before serving an absent build.
- **Regression:** use Render's rollback to a previously validated public-serving deployment, or revert the offending commit and deploy after CI. Do not roll public traffic back to `775c897`, which has no production serving boundary.

Deployment status is intentionally not hardcoded here. Record/share the actual URL only after the live checks pass. Application access logging is disabled; platform logs/metadata are controlled by Render. No submitted scenarios are stored.
