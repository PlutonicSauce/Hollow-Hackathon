"""Release oracles over real Gunicorn HTTP, including recomputation and tampering.

Starts a disposable local production server. Does not load-test the public demo.
Run with the installed backend interpreter from the repository root.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import resource
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
# Hand-calculated/fixture expectations, not a second call to the optimizer.
EXPECTED = {
    "coupled-utility": (1100, {"pump-power", "pump-source-water"}),
    "feeder-cascade": (1080, {"pump-power"}),
    "clinic-priority": (40001, {"clinic-power"}),
    "fairness-tradeoff": (200, {"north-power"}),
    "hand-calculated": (40, set()),
}


def check(base: str) -> dict:
    observations = []

    def request(path: str, body=None, expected=200):
        encoded = None if body is None else json.dumps(body).encode()
        req = Request(base + path, data=encoded, headers={"Content-Type": "application/json"})
        # Respect the real shared admission budget; do not disable hosting limits.
        for attempt in range(4):
            started = time.perf_counter()
            try:
                response = urlopen(req, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read()
                status = response.status
                retry = int(response.headers.get("Retry-After", "2"))
            if status not in {429, 503}:
                break
            if attempt == 3:
                raise AssertionError(f"Admission did not recover: {status}")
            print(f"Admission {status}: waiting {retry}s before retry.", flush=True)
            deadline = time.monotonic() + retry
            while time.monotonic() < deadline:
                time.sleep(min(5, max(0, deadline - time.monotonic())))
        assert status == expected, (path, status, raw[:300])
        data = json.loads(raw)
        observations.append({"path": path, "status": status, "bytes": len(raw),
                             "round_trip_ms": round((time.perf_counter() - started) * 1000, 2)})
        return data

    def verify(receipt, valid=True):
        report = request("/api/verify", {"receipt": receipt})
        assert report["valid"] is valid, report
        statuses = [value for key, value in report.items() if key.endswith("_status")]
        assert len(statuses) == 7
        if valid:
            assert set(statuses) == {"passed"}, report
            assert report["verified_payload_sha256"] == receipt["integrity"]["digest"]
        else:
            assert "failed" in statuses and report["issues"], report
        return report

    def consistency(result):
        scenario = result["scenario"]
        optimization = result["optimization"]
        assert optimization["exhaustive_search_complete"]
        assert optimization["plans_evaluated"] == optimization["feasible_plans"] <= optimization["candidate_plans"]
        plans = {item["baseline"]: item["plan"] for item in optimization["baseline_comparisons"]}
        plans["optimized"] = optimization["selected_plan"]
        assert set(plans) == set(result["traces"])
        for key, trace in result["traces"].items():
            assert [step["minute"] for step in trace] == list(range(scenario["horizon_minutes"] + 1))
            for step in trace:
                assert {asset["asset_id"] for asset in step["assets"]} == {asset["id"] for asset in scenario["assets"]}
                assert all(not asset["service_available"] for asset in step["assets"] if asset["physical_fault_active"])
            metrics = {item["demand_id"]: item for item in plans[key]["demand_metrics"]}
            total = 0
            for demand in scenario["demands"]:
                # The terminal boundary contributes no interval/score.
                served = sum(next(asset for asset in step["assets"] if asset["asset_id"] == demand["served_by_asset_id"])["service_available"] for step in trace[:-1])
                metric = metrics[demand["id"]]
                delivered = served * demand["population"]
                weighted = delivered * demand["priority_weight"]
                assert metric["served_minutes"] == served
                assert metric["service_person_minutes"] == delivered
                assert metric["weighted_service_person_minutes"] == weighted
                assert metric["coverage_parts_per_million"] == served * 1_000_000 // scenario["horizon_minutes"]
                total += weighted
            assert total == plans[key]["objective"]["weighted_service_person_minutes"]
        receipt = result["receipt"]
        assert receipt["payload"]["scenario"] == scenario
        assert receipt["payload"]["selected_trace"] == result["traces"]["optimized"]
        assert receipt["payload"]["recommended_plan"] == optimization["selected_plan"]

    catalog = request("/api/scenarios")
    assert {item["key"] for item in catalog} == set(EXPECTED)
    results = {}
    summary = []
    for key, (score, groups) in EXPECTED.items():
        scenario = request("/api/scenarios/" + key)
        result = request("/api/evaluate", {"scenario": scenario})
        consistency(result)
        selected = result["optimization"]["selected_plan"]
        assert selected["objective"]["weighted_service_person_minutes"] == score
        assert {action["dependency_group_id"] for action in selected["interventions"]} == groups
        verify(result["receipt"])
        results[key] = result
        row = {"scenario": key, "score": score, "candidates": result["optimization"]["candidate_plans"],
               "exact_search_ms": round(result["optimization"]["computation_time_ns"] / 1_000_000, 2),
               "evaluate_http_ms": observations[-2]["round_trip_ms"], "verify_http_ms": observations[-1]["round_trip_ms"]}
        summary.append(row)
        print("PASS:", json.dumps(row), flush=True)

    hand_trace = results["hand-calculated"]["traces"]["optimized"]
    assert [next(asset for asset in step["assets"] if asset["asset_id"] == "scrubber")["service_available"] for step in hand_trace] == [False, False, True, True, True]
    original = results["coupled-utility"]
    for endpoint in ("air-scrubber", "water-distribution"):
        assert [next(asset for asset in step["assets"] if asset["asset_id"] == endpoint)["service_available"] for step in original["traces"]["optimized"]] == [False, True, True, True, True, True, False]
    repeated = request("/api/evaluate", {"scenario": original["scenario"]})
    assert repeated["traces"] == original["traces"]
    assert repeated["receipt"]["payload"] == original["receipt"]["payload"]
    assert repeated["receipt"]["integrity"] == original["receipt"]["integrity"]

    changed = copy.deepcopy(original["scenario"])
    tanker = next(item for item in changed["resources"] if item["id"] == "water-tanker")
    next(item for item in tanker["travel_times"] if item["asset_id"] == "pump")["travel_minutes"] = 5
    recomputed = request("/api/evaluate", {"scenario": changed})
    consistency(recomputed)
    selected = recomputed["optimization"]["selected_plan"]
    assert selected["objective"]["weighted_service_person_minutes"] == 720
    assert {action["target_asset_id"] for action in selected["interventions"]} == {"air-scrubber"}
    assert recomputed["receipt"]["integrity"] != original["receipt"]["integrity"]
    verify(recomputed["receipt"])
    # Historical receipts remain valid for their own inputs; there is no active session on this API.
    verify(original["receipt"])
    manipulated = copy.deepcopy(original["receipt"])
    manipulated["payload"]["recommended_plan"]["objective"]["weighted_service_person_minutes"] += 1
    verify(manipulated, valid=False)
    for receipt in (manipulated, copy.deepcopy(original["receipt"])):
        if receipt is not manipulated:
            receipt["payload"]["scenario"] = changed
        payload_bytes = json.dumps(receipt["payload"], sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        receipt["integrity"]["digest"] = hashlib.sha256(payload_bytes).hexdigest()
        verify(receipt, valid=False)

    fairness = request("/api/evaluate", {"scenario": results["fairness-tradeoff"]["scenario"], "policy": {"primary_tolerance_ppm": 400_000}})
    consistency(fairness)
    assert fairness["optimization"]["selected_plan"]["objective"]["weighted_service_person_minutes"] == 120
    assert fairness["optimization"]["selected_plan"]["objective"]["minimum_community_service_coverage_ppm"] == 500_000
    verify(fairness["receipt"])
    invalid = copy.deepcopy(changed)
    invalid["assets"][0]["id"] = "missing-provider"
    assert request("/api/evaluate", {"scenario": invalid}, expected=422)["code"] == "validation_failed"
    assert request("/api/health") == {"status": "ok"}
    recovered = request("/api/evaluate", {"scenario": results["hand-calculated"]["scenario"]})
    assert recovered["optimization"]["selected_plan"]["objective"]["weighted_service_person_minutes"] == 40
    print("PASS: deterministic repeat, route recomputation 1100→720, historical receipt scope, digest/rehashed tampering, fairness 200→120, invalid references and recovery.", flush=True)
    return {"scenarios": summary, "requests": observations}


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with subprocess.Popen([sys.executable, "-m", "gunicorn", "--config", "backend/gunicorn.conf.py", "engine.public_app:application"], cwd=ROOT, env={**os.environ, "PORT": str(port)}, stdout=subprocess.DEVNULL) as server:
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Production server exited during startup.")
                try:
                    with urlopen(base + "/api/health", timeout=1):
                        break
                except URLError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Production server did not become healthy.")
            report = check(base)
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    report["largest_child_peak_rss_mib"] = round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 2)
    report["memory_note"] = "Largest child-process peak RSS reported by the OS, not summed concurrent service memory or hosted telemetry."
    target = ROOT / ".lifeline" / "release-readiness.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Report: {target}; largest child peak RSS {report['largest_child_peak_rss_mib']} MiB.")


if __name__ == "__main__":
    main()
