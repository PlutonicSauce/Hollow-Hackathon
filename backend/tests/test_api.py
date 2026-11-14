from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from engine.api import LifelineHandler
from engine.models import Scenario
from http.server import ThreadingHTTPServer


class LifelineApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LifelineHandler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        body: object | None = None,
    ) -> tuple[int, dict | list]:
        data = None if body is None else json.dumps(body).encode()
        request = Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_scenario_catalog_and_coupled_scenario_are_backend_fixtures(self) -> None:
        status, catalog = self.request_json("/api/scenarios")
        self.assertEqual(status, 200)
        self.assertIn("coupled-utility", {item["key"] for item in catalog})

        status, scenario_data = self.request_json("/api/scenarios/coupled-utility")
        self.assertEqual(status, 200)
        scenario = Scenario.model_validate(scenario_data)
        self.assertEqual(scenario.id, "coupled-water-power-restoration")
        self.assertEqual(len(scenario.resources), 2)

    def test_evaluate_returns_real_traces_baselines_and_receipt(self) -> None:
        _, scenario = self.request_json("/api/scenarios/coupled-utility")
        status, result = self.request_json(
            "/api/evaluate",
            method="POST",
            body={"scenario": scenario},
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["optimization"]["candidate_plans"], 8)
        self.assertEqual(result["optimization"]["plans_evaluated"], 8)
        self.assertEqual(
            result["optimization"]["selected_plan"]["objective"][
                "weighted_service_person_minutes"
            ],
            1_100,
        )
        self.assertEqual(
            {
                item["baseline"]: item["plan"]["objective"][
                    "weighted_service_person_minutes"
                ]
                for item in result["optimization"]["baseline_comparisons"]
            },
            {"no_intervention": 0, "static_priority": 720, "greedy": 720},
        )
        self.assertEqual(
            set(result["traces"]),
            {"no_intervention", "static_priority", "greedy", "optimized"},
        )
        self.assertEqual(len(result["traces"]["optimized"]), scenario["horizon_minutes"] + 1)

        verify_status, report = self.request_json(
            "/api/verify",
            method="POST",
            body={"receipt": result["receipt"]},
        )
        self.assertEqual(verify_status, 200)
        self.assertTrue(report["valid"], report["issues"])

    def test_resource_and_route_changes_recompute_outcomes(self) -> None:
        _, original = self.request_json("/api/scenarios/coupled-utility")
        without_generator = {
            **original,
            "resources": [
                resource
                for resource in original["resources"]
                if resource["id"] != "mobile-generator"
            ],
        }
        status, resource_result = self.request_json(
            "/api/evaluate",
            method="POST",
            body={"scenario": without_generator},
        )
        self.assertEqual(status, 200)
        resource_plan = resource_result["optimization"]["selected_plan"]
        self.assertLess(
            resource_plan["objective"]["weighted_service_person_minutes"],
            1_100,
        )
        self.assertEqual(resource_plan["interventions"][0]["target_asset_id"], "air-scrubber")

        slow_tanker = json.loads(json.dumps(original))
        tanker = next(item for item in slow_tanker["resources"] if item["id"] == "water-tanker")
        route = next(item for item in tanker["travel_times"] if item["asset_id"] == "pump")
        route["travel_minutes"] = 5
        status, route_result = self.request_json(
            "/api/evaluate",
            method="POST",
            body={"scenario": slow_tanker},
        )
        self.assertEqual(status, 200)
        route_plan = route_result["optimization"]["selected_plan"]
        self.assertEqual(
            route_plan["objective"]["weighted_service_person_minutes"],
            720,
        )
        self.assertEqual(route_plan["interventions"][0]["target_asset_id"], "air-scrubber")

    def test_invalid_scenario_and_malformed_json_return_clear_errors(self) -> None:
        status, response = self.request_json(
            "/api/evaluate",
            method="POST",
            body={"scenario": {"id": "incomplete"}},
        )
        self.assertEqual(status, 422)
        self.assertEqual(response["error"], "Scenario or policy validation failed.")
        self.assertTrue(response["details"])

        request = Request(
            self.base_url + "/api/evaluate",
            data=b"{",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=10)
        self.assertEqual(error.exception.code, 400)
        with error.exception:
            self.assertIn("Invalid JSON", error.exception.read().decode())

    def test_candidate_limit_is_reported_as_a_bounded_search_error(self) -> None:
        _, scenario = self.request_json("/api/scenarios/coupled-utility")
        status, response = self.request_json(
            "/api/evaluate",
            method="POST",
            body={
                "scenario": scenario,
                "policy": {"max_candidate_plans": 2},
            },
        )
        self.assertEqual(status, 422)
        self.assertEqual(response["code"], "search_limit_exceeded")


if __name__ == "__main__":
    unittest.main()
