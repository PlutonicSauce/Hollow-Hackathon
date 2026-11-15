# Public demo security

LIFELINE is a synthetic decision-support prototype, not an emergency operating system. A verified receipt establishes consistency with the declared model; it proves neither physical accuracy nor authorship. Do not submit personal, confidential, or operational incident data.

## Serving boundary

Public deployments use `scripts/start.sh`: Gunicorn, one worker, four HTTP threads, at most 16 connections, and a backlog of 16. Only the built frontend and explicit API routes are served. There are no directory listings, arbitrary file routes, database, file uploads, cookies, or authentication. `python -m engine.api` remains a loopback-only development server and must not be exposed publicly.

Render terminates HTTPS and redirects HTTP. The application trusts forwarded HTTPS information only because its hosted port sits behind Render ingress; do not reuse that trust configuration on an unprotected host. Responses include CSP, frame denial, MIME sniffing protection, a no-referrer policy, and disabled camera/microphone/location permissions. HSTS is sent on HTTPS. Legacy Google Fonts origins remain allowed by CSP, although the current UI uses system fonts and makes no font requests; inline styles are needed by the current React interface. Scripts and API connections are same-origin. No CORS permissions are granted.

## Admission and execution limits

The public API applies these limits equally to evaluation scenarios and scenarios inside receipts, before simulation or verification. The underlying versioned engine and receipt format are unchanged.

| Input | Public maximum |
| --- | --- |
| Request / response | 2,000,000 / 8,000,000 bytes |
| JSON shape | 32 levels, 60,000 values including keys; 256 keys/object; 4,096 entries/array; 32,768 characters/string; integer magnitude ≤ 10²⁰ |
| Scenario | 24 assets, 32 demands, 32 faults, 4 resources, 4 interventions; horizon 60 minutes |
| Graph | 4 groups/asset, 8 providers/group; 64 total groups, 128 provider edges; DAG contract still required |
| Resource | 24 routes and 5 distinct capabilities |
| Scenario scalar values | Strings ≤128 characters; integer magnitude ≤1,000,000 (keeps generated scores within JavaScript's exact integer range) |
| Search | 256 raw idle-or-assignment candidates, regardless of a larger client-declared policy limit |
| Combined work | candidates × (horizon + 1) × (assets + groups + provider edges + demands) ≤1,000,000 |

Only **one** computation/upload is admitted at a time; competing computation requests receive 503. A shared rolling limit permits 12 computation requests per minute, including invalid requests admitted for processing. It uses no client-supplied IP headers. Static files and health checks do not consume that budget. This deliberately favors bounded resource use over throughput; it is not a guarantee of availability against abuse.

Evaluation and verification run in disposable subprocesses. Each has an 8-second wall deadline; the parent kills and reaps it on expiry. OS limits impose 6 seconds of CPU time (7-second hard limit), no core dumps, and, on Linux hosting, 256 MiB of virtual address space. The memory limit is not enabled on macOS because its address-space behavior differs. A failed/killed job never returns a partial optimum or successful verification. Computation is not delegated to a timed-out background thread.

Uploads require JSON and Content-Length; chunked bodies are rejected. A socket shutdown interrupts incomplete/trickling body reads after 5 seconds. Gunicorn bounds request lines and headers. Its 30-second worker liveness timeout is **not** the computation deadline. Server/framework parsing errors may use Gunicorn's generic error response; application errors are JSON and never include server exception text or stack traces.

## Data and maintenance

Requests are handled in memory and not persisted. Application access logs are disabled; Render may retain platform request metadata and server lifecycle logs. Receipts can include every submitted scenario field, so treat them as public data. No secrets are required or committed. Keep provider credentials in the provider account, not in this repository. Runtime dependencies and Node packages are pinned; update them deliberately and rerun CI.

Report a vulnerability privately to `seshank0830@gmail.com` with reproduction details, without real incident data or credentials. This limited demo is not a security audit or a safety certification.
