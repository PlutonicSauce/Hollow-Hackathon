"""Local HTTP API for the LIFELINE interactive demonstration."""

from __future__ import annotations

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from .models import Intervention, OptimizationPolicy, Scenario
from .optimizer import OptimizationLimitError, optimize_interventions
from .certificates import build_coordination_certificate, verify_coordination_certificate
from .receipts import create_decision_receipt
from .scenarios import (
    coupled_utility_scenario,
    downstream_priority_scenario,
    fairness_tradeoff_scenario,
    hand_calculated_scenario,
    signature_scenario,
)
from .simulation import simulate
from .verification import verify_decision_receipt

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"
MAX_REQUEST_BYTES = 2_000_000
ScenarioFactory = Callable[[], Scenario]

SCENARIOS: dict[str, tuple[str, str, ScenarioFactory]] = {
    "coupled-utility": (
        "Coupled utility failure",
        "Two crews must restore both pump inputs to recover ventilation and community water.",
        coupled_utility_scenario,
    ),
    "feeder-cascade": (
        "Feeder cascade",
        "Compare upstream pump support with a direct clinic intervention.",
        signature_scenario,
    ),
    "clinic-priority": (
        "Clinic-priority incident",
        "A concentrated medical demand can make downstream support preferable.",
        downstream_priority_scenario,
    ),
    "fairness-tradeoff": (
        "Coverage trade-off",
        "Explore the configured primary-score tolerance and minimum demand coverage.",
        fairness_tradeoff_scenario,
    ),
    "hand-calculated": (
        "Reserve boundary example",
        "A small OR/AND cascade with a manually checkable reserve trace.",
        hand_calculated_scenario,
    ),
}


def scenario_catalog() -> list[dict[str, str]]:
    return [
        {"key": key, "name": name, "description": description}
        for key, (name, description, _) in SCENARIOS.items()
    ]


def _scenario_with_interventions(
    scenario: Scenario, interventions: tuple[Intervention, ...]
) -> Scenario:
    data = scenario.model_dump(mode="python")
    data["interventions"] = interventions
    return Scenario.model_validate(data)


def evaluate_scenario(
    scenario: Scenario,
    policy: OptimizationPolicy | None = None,
) -> dict[str, Any]:
    result = optimize_interventions(scenario, policy)
    baselines = {item.baseline.value: item for item in result.baseline_comparisons}
    plans = {
        "no_intervention": (),
        "static_priority": baselines["static_priority"].plan.interventions,
        "greedy": baselines["greedy"].plan.interventions,
        "optimized": result.selected_plan.interventions,
    }
    traces = {}
    for name, interventions in plans.items():
        replay_scenario = _scenario_with_interventions(scenario, interventions)
        traces[name] = simulate(replay_scenario).model_dump(mode="json")["steps"]
    receipt = create_decision_receipt(scenario, result)
    certificate = build_coordination_certificate(scenario, result.selected_plan.interventions)
    certificate_report = verify_coordination_certificate(scenario, certificate)
    if certificate_report.status != "passed":
        raise ValueError("Generated coordination evidence did not pass replay checks.")
    return {
        "scenario": scenario.model_dump(mode="json"),
        "no_intervention_simulation": simulate(scenario).model_dump(mode="json"),
        "optimization": result.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json"),
        "coordination_certificate": certificate.model_dump(mode="json"),
        "coordination_verification": certificate_report.model_dump(mode="json"),
        "traces": traces,
    }


class LifelineHandler(SimpleHTTPRequestHandler):
    server_version = "LIFELINE/1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(FRONTEND_DIST), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(200, {"status": "ok"})
            return
        if path == "/api/scenarios":
            self._send_json(200, scenario_catalog())
            return
        if path.startswith("/api/scenarios/"):
            key = unquote(path.removeprefix("/api/scenarios/"))
            entry = SCENARIOS.get(key)
            if entry is None:
                self._send_json(404, {"error": "Unknown scenario."})
                return
            self._send_json(200, entry[2]().model_dump(mode="json"))
            return
        if path.startswith("/api/"):
            self._send_json(404, {"error": "Unknown API endpoint."})
            return
        if not FRONTEND_DIST.is_dir() or not (FRONTEND_DIST / "index.html").is_file():
            self._send_json(
                503,
                {"error": "Frontend build is missing. Run npm run build in frontend/."},
            )
            return
        requested = (FRONTEND_DIST / path.lstrip("/")).resolve()
        if (
            FRONTEND_DIST.resolve() not in requested.parents
            or not requested.is_file()
        ):
            self.path = "/"
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            data = self._read_json()
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            self._send_json(400, {"error": f"Invalid JSON: {error}"})
            return
        except ValueError as error:
            self._send_json(413, {"error": str(error)})
            return
        if not isinstance(data, dict):
            self._send_json(400, {"error": "Request JSON must be an object."})
            return

        if path == "/api/evaluate":
            try:
                scenario = Scenario.model_validate(data.get("scenario"))
                policy_data = data.get("policy")
                policy = (
                    OptimizationPolicy.model_validate(policy_data)
                    if policy_data is not None
                    else None
                )
                self._send_json(200, evaluate_scenario(scenario, policy))
            except ValidationError as error:
                details = [
                    {
                        "location": list(item["loc"]),
                        "type": item["type"],
                        "message": item["msg"],
                    }
                    for item in error.errors()
                ]
                self._send_json(422, {"error": "Scenario or policy validation failed.", "details": details})
            except OptimizationLimitError as error:
                self._send_json(422, {"error": str(error), "code": "search_limit_exceeded"})
            except ValueError as error:
                self._send_json(422, {"error": str(error), "code": "invalid_scenario"})
            return

        if path == "/api/verify":
            report = verify_decision_receipt(data.get("receipt", data))
            self._send_json(200, report.model_dump(mode="json"))
            return

        self._send_json(404, {"error": "Unknown API endpoint."})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[lifeline-api] {self.address_string()} {format % args}")

    def _read_json(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Content-Length must be an integer.") from error
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError(f"Request body must be between 1 and {MAX_REQUEST_BYTES} bytes.")
        return json.loads(self.rfile.read(length))

    def _send_json(self, status: int, data: Any) -> None:
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8000), LifelineHandler)
    print("LIFELINE API listening at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping LIFELINE API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
