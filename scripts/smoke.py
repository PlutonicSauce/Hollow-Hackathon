"""Check the real production server, or an already deployed HTTPS origin."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def check(base: str, *, local_port: int | None = None) -> None:
    def request(path: str, data=None, *, raw=None, headers=None):
        body = json.dumps(data).encode() if data is not None else raw
        req = Request(base + path, data=body, headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = urlopen(req, timeout=120 if path == "/api/health" else 15)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    assert request("/api/health")[0] == 200
    status, headers, html = request("/")
    assert status == 200 and b'LIFELINE' in html
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    if base.startswith("https://"):
        assert headers["Strict-Transport-Security"]
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html.decode())
    assert assets and all(request(path)[0] == 200 for path in assets)
    for path in ("/.git/config", "/assets/../README.md", "/assets/", "/backend/engine/api.py"):
        status, _, raw = request(path)
        assert status == 404 and b"Traceback" not in raw and b"/Users/" not in raw
    status, _, raw = request("/api/scenarios/coupled-utility")
    assert status == 200
    scenario = json.loads(raw)
    started = time.monotonic()
    status, _, raw = request("/api/evaluate", {"scenario": scenario})
    elapsed = (time.monotonic() - started) * 1000
    assert status == 200, raw
    result = json.loads(raw)
    optimization = result["optimization"]
    assert optimization["candidate_plans"] == optimization["plans_evaluated"] == 8
    assert optimization["selected_plan"]["objective"]["weighted_service_person_minutes"] == 1100
    assert {item["baseline"]: item["plan"]["objective"]["weighted_service_person_minutes"]
            for item in optimization["baseline_comparisons"]} == {"no_intervention": 0, "static_priority": 720, "greedy": 720}
    status, _, raw = request("/api/verify", {"receipt": result["receipt"]})
    report = json.loads(raw)
    assert status == 200 and report["valid"], raw
    assert all(value == "passed" for key, value in report.items() if key.endswith("_status"))
    assert report["verified_payload_sha256"] == "9943a7ec141f32bc66cd609379541c85d3e598528799a3ac7351efaa515090a2"
    oversized = {**scenario, "horizon_minutes": 61}
    for operation, data in (("evaluate", {"scenario": oversized}),
                            ("verify", {"receipt": {"payload": {"scenario": oversized}}})):
        status, _, raw = request(f"/api/{operation}", data)
        assert status == 422 and json.loads(raw)["code"] == "public_limit_exceeded"
    assert request("/api/evaluate", raw=b"{")[0] == 400
    assert request("/api/evaluate", raw=b"{}", headers={"Content-Type": "text/plain"})[0] == 415
    print(f"PASS: same-origin frontend/assets, 1100 vs 720, 8 candidates, 7 receipt checks; evaluation {elapsed:.1f} ms (one sample).")
    print("PASS: security headers, filesystem denial, malformed input, evaluation and verification limits.")

    if local_port is not None:
        status, forwarded_headers, _ = request("/api/health", headers={"X-Forwarded-Proto": "https"})
        assert status == 200 and forwarded_headers["Strict-Transport-Security"]
        # Withhold an upload while checking concurrent admission and health.
        with socket.create_connection(("127.0.0.1", local_port), timeout=8) as slow:
            slow.sendall(b"POST /api/evaluate HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n{")
            time.sleep(0.1)
            deadline = time.monotonic() + 2
            while request("/api/evaluate", raw=b"{}")[0] != 503:
                assert time.monotonic() < deadline, "Concurrent request was not rejected."
                time.sleep(0.02)
            assert request("/api/health")[0] == 200
            started = time.monotonic()
            response = slow.recv(4096)
            assert b"408 Request Timeout" in response and time.monotonic() - started < 7
        # Saturation checks stay local: do not monopolize the deployed demo.
        for _ in range(13):
            status, _, _ = request("/api/evaluate", raw=b"{")
            if status == 429:
                break
        assert status == 429
        assert request("/api/health")[0] == 200
        print("PASS: real HTTP busy rejection, responsive health, 5-second upload cutoff, global rate limit.")


def main() -> None:
    if len(sys.argv) > 1:
        base = sys.argv[1].rstrip("/")
        if not base.startswith("https://"):
            raise SystemExit("Public checks require an HTTPS origin.")
        check(base)
        return
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {**os.environ, "PORT": str(port)}
    # Use this interpreter, so the check exercises the installed locked runtime.
    with subprocess.Popen([sys.executable, "-m", "gunicorn", "--config", "backend/gunicorn.conf.py", "engine.public_app:application"],
                          cwd=ROOT, env=environment, stdout=subprocess.DEVNULL) as server:
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Production server exited during startup.")
                try:
                    with urlopen(base + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except URLError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Production server did not become healthy.")
            check(base, local_port=port)
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
