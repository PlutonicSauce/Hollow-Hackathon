# LIFELINE public API

The frontend and API share one origin. Requests and successful responses use JSON. The public service accepts only the supported small scenarios in [SECURITY.md](./SECURITY.md); stricter public admission does not alter the deterministic model or receipt schema.

| Method and path | Behavior |
| --- | --- |
| `GET /api/health` | `200 {"status":"ok"}`; no computation, not a readiness benchmark |
| `GET /api/scenarios` | Scenario catalog: `key`, `name`, `description` |
| `GET /api/scenarios/{key}` | Complete scenario input; unknown key is 404 |
| `POST /api/evaluate` | Body: `{"scenario": {...}, "policy": {"primary_tolerance_ppm": 0}}`; policy is optional |
| `POST /api/verify` | Body: `{"receipt": {...}}` or the receipt object directly; JSON strings containing receipts are not accepted by the public HTTP boundary |

Use `Content-Type: application/json` and Content-Length for POSTs. Ordinary HTTP/1.1 clients set the length automatically; hosted browser HTTP/2 traffic is framed by Render ingress before reaching Gunicorn. No API key, cookies, or CORS access is provided. `HEAD` supports the GET routes; unsupported methods return 405.

Evaluation returns `scenario`, `no_intervention_simulation`, `optimization`, `receipt`, and `traces`. The four trace keys are `no_intervention`, `static_priority`, `greedy`, and `optimized`. Scores are weighted service-person-minutes, never lives saved. Policy fields are `primary_tolerance_ppm` (0–1,000,000) and optional positive `max_candidate_plans` (engine default 100,000). A smaller declared candidate limit is honored; a larger one cannot bypass the public 256-candidate/work cap. Policy values are retained in the receipt without rewriting its digest semantics.

Verification independently reconstructs/replays the selected plan, derives metrics, recomputes baselines, and enumerates the bounded assignment space without calling the optimizer. It shares the versioned simulator. A normal verification report has `valid`, seven `*_status` fields, `issues`, `verified_payload_sha256`, and measured `verification_duration_ns`. An invalid/tampered receipt normally returns **200 with `valid:false`**. Malformed scenario contracts or public execution/admission violations instead return a 4xx error; they must not be interpreted as a verification pass.

## Receipt scope and edited inputs

The API is stateless: it verifies the scenario recorded in the receipt, not a session's current draft. An unchanged historical receipt can still pass after someone evaluates a different scenario. The frontend invalidates its verification state on any edit, disables verification until recomputation, and ignores in-flight verification responses from older input revisions. Substituting new inputs into an old receipt fails integrity; rehashing that substitution still fails replay/baseline/optimality evidence. This does not provide freshness, authorship or trusted timestamps.

## Errors

Application failures use `{"error":"Human-readable message.","code":"machine_code"}`. Contract errors may include up to 16 field locations/types without submitted values. Do not depend on exact error wording.

| Status | Meaning / representative code |
| --- | --- |
| 400 | Malformed JSON, wrong envelope, unsupported body framing |
| 404 / 405 | Unknown route / unsupported method |
| 408 / 411 | Incomplete upload / missing Content-Length |
| 413 / 415 | Body too large / unsupported content type |
| 422 | `validation_failed`, `invalid_input`, `search_limit_exceeded`, `public_limit_exceeded`, or `execution_limit_exceeded` |
| 429 | `rate_limit_exceeded`; global computation budget, `Retry-After: 60` |
| 503 | `server_busy`; one job already admitted, `Retry-After: 2` |
| 500 | Redacted `internal_error` |

Retry 429/503 only after waiting. Simplify a scenario that exceeds model/work limits. Do not retry an execution-limit failure in a tight loop. Proxy-level failures or a Render cold-start page can be non-JSON.

## End-to-end check

From the repository root, after setup/build:

```sh
backend/.venv/bin/python scripts/smoke.py
# After deployment, substitute the actual HTTPS origin:
backend/.venv/bin/python scripts/smoke.py https://YOUR-SERVICE.onrender.com
```

The script loads the production frontend/assets, evaluates the 8-plan coupled scenario (1,100 versus 720/720 and no response 0), verifies all seven receipt checks and the known digest, and checks public input/security responses. Local mode also checks live concurrency, slow-upload termination, and rate saturation. It starts/stops its own production server; remote mode never performs saturation checks.
