"""Public admission, HTTP boundary, and actual process termination checks."""

from __future__ import annotations

import copy
import io
import json
import signal
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from engine import public_app
from engine.api import evaluate_scenario
from engine.public_limits import PublicLimitError, check_json_shape, validate_public_scenario
from engine.public_worker import execute
from engine.scenarios import coupled_utility_scenario


def fixture() -> dict:
    return coupled_utility_scenario().model_dump(mode="json")


class PublicAdmissionTests(unittest.TestCase):
    def test_supported_boundaries_and_original_receipt_are_unchanged(self) -> None:
        data = fixture()
        data["id"] = "x" * 128
        data["horizon_minutes"] = 60
        data["demands"][0]["population"] = 1_000_000
        self.assertEqual(validate_public_scenario(data).horizon_minutes, 60)

        original = evaluate_scenario(coupled_utility_scenario())
        with patch("engine.optimizer.optimize_interventions", side_effect=AssertionError("Must not optimize during verification")):
            status, report = execute("verify", json.dumps({"receipt": original["receipt"]}).encode())
        self.assertEqual(status, 200)
        self.assertTrue(report["valid"], report)
        self.assertEqual(report["verified_payload_sha256"], "9943a7ec141f32bc66cd609379541c85d3e598528799a3ac7351efaa515090a2")

    def test_public_scenario_limits_apply_to_evaluation_and_receipts(self) -> None:
        mutations = [
            ("horizon_minutes", 61), ("id", "x" * 129),
            ("assets", fixture()["assets"] * 5),
            ("demands", fixture()["demands"] * 17),
            ("faults", fixture()["faults"] * 17),
            ("resources", fixture()["resources"] * 3),
            ("interventions", [{}] * 5),
        ]
        for key, value in mutations:
            data = {**fixture(), key: value}
            for operation, request in (
                ("evaluate", {"scenario": data}),
                ("verify", {"receipt": {"payload": {"scenario": data}}}),
            ):
                with self.subTest(key=key, operation=operation):
                    status, body = execute(operation, json.dumps(request).encode())
                    self.assertEqual(status, 422)
                    self.assertEqual(body["code"], "public_limit_exceeded")

    def test_nested_graph_and_route_limits_precede_contract_validation(self) -> None:
        for field in ("groups", "providers", "routes", "integer"):
            data = fixture()
            if field == "groups":
                data["assets"][0]["dependency_groups"] = [{}] * 5
            elif field == "providers":
                asset = next(item for item in data["assets"] if item["dependency_groups"])
                asset["dependency_groups"][0]["provider_asset_ids"] = ["x"] * 9
            elif field == "routes":
                data["resources"][0]["travel_times"] = [{}] * 25
            else:
                data["demands"][0]["population"] = 1_000_001
            with self.subTest(field=field), self.assertRaises(PublicLimitError):
                validate_public_scenario(data)

    def test_total_provider_edges_are_bounded(self) -> None:
        buffer = fixture()["assets"][0]["buffer"]
        sources = [{"id": f"s{i}", "name": "source", "kind": "source", "provides": "power", "buffer": buffer} for i in range(8)]
        targets = [{"id": f"t{i}", "name": "target", "kind": "facility", "provides": "power", "buffer": buffer,
                    "dependency_groups": [{"id": f"g{i}-{j}", "service_type": "power", "provider_asset_ids": [s["id"] for s in sources]}
                                          for j in range(4)]} for i in range(5)]
        with self.assertRaisesRegex(PublicLimitError, "provider edges"):
            validate_public_scenario({"id": "dense", "horizon_minutes": 6, "assets": sources + targets})

    def test_candidate_cap_cannot_be_raised_by_evaluation_or_receipt_policy(self) -> None:
        data = fixture()
        tanker = data["resources"][1]
        boundary = {**data, "resources": [{**tanker, "id": f"crew-{i}"} for i in range(4)]}
        self.assertEqual(len(validate_public_scenario(boundary).resources), 4)
        data["resources"] = [{**tanker, "id": f"crew-{i}", "capabilities": ["power", "water"]} for i in range(4)]
        for operation, request in (
            ("evaluate", {"scenario": data, "policy": {"max_candidate_plans": 10**18}}),
            ("verify", {"receipt": {"payload": {"scenario": data, "optimization_policy": {"max_candidate_plans": 10**18}}}}),
        ):
            status, body = execute(operation, json.dumps(request).encode())
            self.assertEqual(status, 422)
            self.assertIn("256 candidate", body["error"])

    def test_combined_work_budget_rejects_individually_allowed_dimensions(self) -> None:
        data = fixture()
        data["horizon_minutes"] = 60
        tanker = data["resources"][1]
        data["resources"] = [{**tanker, "id": f"crew-{i}"} for i in range(4)]
        source = next(asset for asset in data["assets"] if asset["kind"] == "source" and asset["provides"] == "power")
        for i in range(18):
            data["assets"].append({**copy.deepcopy(source), "id": f"extra-{i}", "kind": "facility",
                                   "dependency_groups": [{"id": f"group-{i}-{j}", "service_type": "power", "provider_asset_ids": [source["id"]]} for j in range(2)]})
        data["demands"] = [{**data["demands"][0], "id": f"demand-{i}"} for i in range(32)]
        with self.assertRaisesRegex(PublicLimitError, "work budget"):
            validate_public_scenario(data)

    def test_json_depth_size_and_malformed_input_are_bounded(self) -> None:
        nested: object = None
        for _ in range(34):
            nested = [nested]
        for value in (nested, [None] * 4097, "x" * 32_769, 10**21, {str(i): None for i in range(257)}):
            with self.subTest(kind=type(value)), self.assertRaises(PublicLimitError):
                check_json_shape(value)
        for raw in (b'{', b'\xff', b'{"x":1,"x":2}', b'{"x":NaN}', b'[' * 2000):
            status, body = execute("evaluate", raw)
            self.assertIn(status, {400, 422})
            self.assertNotIn("Traceback", json.dumps(body))


class PublicHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        public_app._admitted.clear()

    def request(self, path: str, body: bytes = b"{}", method: str = "POST", **extra):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": method, "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body), "wsgi.url_scheme": "https", **extra}
        response = []
        result = b"".join(public_app.application(environ, lambda status, headers: response.append((int(status.split()[0]), dict(headers)))))
        return *response[0], result

    def test_real_process_evaluation_and_verification(self) -> None:
        status, headers, raw = self.request("/api/evaluate", json.dumps({"scenario": fixture()}).encode())
        self.assertEqual(status, 200, raw)
        result = json.loads(raw)
        optimization = result["optimization"]
        self.assertEqual(optimization["candidate_plans"], 8)
        self.assertEqual(optimization["best_primary_score"], 1100)
        self.assertEqual([item["plan"]["objective"]["weighted_service_person_minutes"] for item in optimization["baseline_comparisons"]], [0, 720, 720])
        status, _, raw = self.request("/api/verify", json.dumps({"receipt": result["receipt"]}).encode())
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["valid"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn("Strict-Transport-Security", headers)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_payload_framing_methods_and_content_types(self) -> None:
        cases = [
            ({"CONTENT_LENGTH": "2000001"}, 413), ({"CONTENT_LENGTH": ""}, 411),
            ({"CONTENT_LENGTH": "-1"}, 413), ({"CONTENT_TYPE": "text/plain"}, 415),
            ({"HTTP_TRANSFER_ENCODING": "chunked"}, 400), ({"CONTENT_LENGTH": "10"}, 408),
        ]
        for extra, expected in cases:
            with self.subTest(extra=extra):
                self.assertEqual(self.request("/api/evaluate", **extra)[0], expected)
        self.assertEqual(self.request("/api/evaluate", method="OPTIONS")[0], 405)
        self.assertEqual(self.request("/api/unknown")[0], 404)

    def test_no_filesystem_exposure_or_directory_listing(self) -> None:
        for path in ("/.git/config", "/backend/pyproject.toml", "/assets/", "/assets/../../README.md", "/assets/missing.js", "/api/unknown"):
            with self.subTest(path=path):
                status, _, raw = self.request(path, method="GET")
                self.assertEqual(status, 404)
                self.assertNotIn(b"/Users/", raw)

    def test_unexpected_errors_are_redacted(self) -> None:
        with patch.object(public_app, "run_computation", side_effect=RuntimeError("/secret/path TOKEN private stack")):
            status, _, raw = self.request("/api/evaluate")
        self.assertEqual(status, 500)
        self.assertNotIn(b"secret", raw)
        self.assertNotIn(b"TOKEN", raw)

    def test_busy_rejects_both_operations_while_health_remains_available(self) -> None:
        entered, finish = threading.Event(), threading.Event()
        def slow(*args):
            entered.set()
            finish.wait(2)
            return 200, b"{}"
        with patch.object(public_app, "run_computation", side_effect=slow):
            thread = threading.Thread(target=lambda: self.request("/api/evaluate"))
            thread.start()
            try:
                self.assertTrue(entered.wait(1))
                for operation in ("evaluate", "verify"):
                    status, headers, _ = self.request(f"/api/{operation}")
                    self.assertEqual(status, 503)
                    self.assertEqual(headers["Retry-After"], "2")
                self.assertEqual(self.request("/api/health", method="GET")[0], 200)
            finally:
                finish.set()
                thread.join(2)

    def test_global_rate_is_bounded_without_trusting_forwarded_ip(self) -> None:
        with patch.object(public_app, "run_computation", return_value=(400, b"{}")):
            for i in range(12):
                self.assertEqual(self.request("/api/evaluate", HTTP_X_FORWARDED_FOR=f"192.0.2.{i}")[0], 400)
            status, headers, raw = self.request("/api/verify")
            self.assertEqual(status, 429)
            self.assertEqual(headers["Retry-After"], "60")
            self.assertEqual(json.loads(raw)["code"], "rate_limit_exceeded")


class ProcessLimitTests(unittest.TestCase):
    def test_wall_deadline_really_kills_and_reaps_cpu_work(self) -> None:
        real_popen = subprocess.Popen
        children = []
        def spawn(*args, **kwargs):
            child = real_popen([sys.executable, "-c", "while True: pass"], **kwargs)
            children.append(child)
            return child
        with patch.object(public_app.subprocess, "Popen", side_effect=spawn), patch.object(public_app, "WALL_SECONDS", 0.2):
            status, raw = public_app.run_computation("verify", b"{}")
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(raw)["code"], "execution_limit_exceeded")
        self.assertEqual(children[0].returncode, -signal.SIGKILL)
        self.assertIsNotNone(children[0].poll())

    @unittest.skipUnless(sys.platform == "linux", "Linux hosting RLIMIT_AS check")
    def test_linux_memory_limit_is_real(self) -> None:
        code = "from engine import public_worker as w; w.execute=lambda *args: (200, {'data': 'x' * (300 * 1024 * 1024)}); w.main()"
        result = subprocess.run([sys.executable, "-c", code, "evaluate"], input=b"{}", capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"execution_limit_exceeded", result.stdout)

    def test_cpu_limit_terminates_worker_without_parent_timeout(self) -> None:
        code = "from engine import public_worker as w\nw.CPU_SECONDS=1\ndef busy(*args):\n while True: pass\nw.execute=busy\nw.main()"
        result = subprocess.run([sys.executable, "-c", code, "evaluate"], input=b"{}", capture_output=True, timeout=5)
        self.assertIn(result.returncode, {-signal.SIGXCPU, -signal.SIGKILL})


if __name__ == "__main__":
    unittest.main()
