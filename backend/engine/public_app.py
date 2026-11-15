"""Same-origin WSGI frontend/API boundary for the public synthetic demo."""

from __future__ import annotations

import json
import mimetypes
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from http import HTTPStatus

from .api import FRONTEND_DIST, SCENARIOS, scenario_catalog
from .public_limits import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, WALL_SECONDS

BODY_SECONDS = 5
RATE_REQUESTS = 12
RATE_SECONDS = 60
_compute_slot = threading.BoundedSemaphore(1)
_rate_lock = threading.Lock()
_admitted: deque[float] = deque()

SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    ("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
     "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
     "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
     "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"),
]


def run_computation(operation: str, raw: bytes) -> tuple[int, bytes]:
    """Kill AND reap on deadline; no background thread continues doing work."""
    with subprocess.Popen(
        [sys.executable, "-m", "engine.public_worker", operation],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ) as process:
        try:
            output, _ = process.communicate(raw, timeout=WALL_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            return _json_error(422, "execution_limit_exceeded", "Computation exceeded the execution deadline.")
        if process.returncode != 0:
            return _json_error(422, "execution_limit_exceeded", "Computation exceeded a resource limit or stopped unexpectedly.")
    if len(output) > MAX_RESPONSE_BYTES + 4:
        return _json_error(422, "public_limit_exceeded", "Result exceeds the public response limit.")
    status, separator, body = output.partition(b"\n")
    if not separator or status not in {b"200", b"400", b"404", b"422", b"500"}:
        return _json_error(500, "internal_error", "Computation failed.")
    return int(status), body


def _json_error(status: int, code: str, message: str) -> tuple[int, bytes]:
    return status, json.dumps({"error": message, "code": code}).encode()


def _json(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()


def _read_body(environ: dict, length: int) -> bytes:
    # Gunicorn supplies its socket in the WSGI environment. A real socket shutdown
    # interrupts slow/trickling uploads, rather than timing out a waiting thread.
    sock = environ.get("gunicorn.socket")
    timer = None
    if sock is not None:
        sock.settimeout(BODY_SECONDS)
        def stop_upload() -> None:
            try:
                sock.shutdown(socket.SHUT_RD)
            except OSError:
                pass
        timer = threading.Timer(BODY_SECONDS, stop_upload)
        timer.daemon = True
        timer.start()
    try:
        return environ["wsgi.input"].read(length)
    finally:
        if timer is not None:
            timer.cancel()


def _post(environ: dict, operation: str) -> tuple[int, bytes]:
    if environ.get("HTTP_TRANSFER_ENCODING"):
        return _json_error(400, "invalid_request", "Transfer-Encoding is not supported; send Content-Length.")
    if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
        return _json_error(415, "unsupported_media_type", "Use application/json.")
    try:
        length = int(environ.get("CONTENT_LENGTH", ""))
    except ValueError:
        return _json_error(411, "length_required", "A valid Content-Length is required.")
    if not 0 < length <= MAX_REQUEST_BYTES:
        return _json_error(413, "payload_too_large", f"Request body must be 1–{MAX_REQUEST_BYTES} bytes.")
    if not _compute_slot.acquire(blocking=False):
        return _json_error(503, "server_busy", "One computation is already running. Retry shortly.")
    try:
        now = time.monotonic()
        with _rate_lock:
            while _admitted and _admitted[0] <= now - RATE_SECONDS:
                _admitted.popleft()
            if len(_admitted) >= RATE_REQUESTS:
                return _json_error(429, "rate_limit_exceeded", "Public demo allows 12 computation requests per minute in total.")
            _admitted.append(now)
        try:
            raw = _read_body(environ, length)
        except (OSError, ValueError):
            return _json_error(408, "request_timeout", "Request upload did not complete.")
        if len(raw) != length:
            return _json_error(408, "request_timeout", "Request upload did not complete.")
        return run_computation(operation, raw)
    finally:
        _compute_slot.release()


def _static(path: str) -> tuple[int, bytes, str]:
    root = FRONTEND_DIST.resolve()
    target = (root / path.lstrip("/")).resolve()
    if path == "/":
        target = root / "index.html"
    elif not path.startswith("/assets/") or target.suffix not in {".js", ".css", ".svg", ".png", ".jpg", ".webp", ".woff2"}:
        status, body = _json_error(404, "not_found", "Not found.")
        return status, body, "application/json"
    if not target.is_relative_to(root) or not target.is_file():
        status, body = _json_error(404, "not_found", "Not found.")
        return status, body, "application/json"
    return 200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream"


def application(environ: dict, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    content_type = "application/json"
    try:
        if method in {"GET", "HEAD"}:
            if path == "/api/health":
                status, body = 200, _json({"status": "ok"})
            elif path == "/api/scenarios":
                status, body = 200, _json(scenario_catalog())
            elif path.startswith("/api/scenarios/") and path.removeprefix("/api/scenarios/") in SCENARIOS:
                entry = SCENARIOS[path.removeprefix("/api/scenarios/")]
                status, body = 200, _json(entry[2]().model_dump(mode="json"))
            else:
                status, body, content_type = _static(path)
        elif method == "POST" and path in {"/api/evaluate", "/api/verify"}:
            status, body = _post(environ, path.removeprefix("/api/"))
        elif method not in {"GET", "HEAD", "POST"}:
            status, body = _json_error(405, "method_not_allowed", "Method not allowed.")
        else:
            status, body = _json_error(404, "not_found", "Not found.")
    except Exception:
        status, body = _json_error(500, "internal_error", "Request could not be completed.")
    headers = [*SECURITY_HEADERS, ("Content-Type", content_type),
               ("Content-Length", str(len(body))), ("Cache-Control", "no-store")]
    if environ.get("wsgi.url_scheme") == "https":
        headers.append(("Strict-Transport-Security", "max-age=31536000"))
    if status in {429, 503}:
        headers.append(("Retry-After", "60" if status == 429 else "2"))
    if status == 405:
        headers.append(("Allow", "GET, HEAD, POST"))
    start_response(f"{status} {HTTPStatus(status).phrase}", headers)
    return [b"" if method == "HEAD" else body]
