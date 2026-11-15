"""Disposable, OS-limited computation process. Never serves HTTP itself."""

from __future__ import annotations

import json
import resource
import sys

from .public_limits import (
    CPU_SECONDS, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, MEMORY_BYTES,
    PublicLimitError, check_json_shape, validate_public_scenario,
)


def execute(operation: str, raw: bytes) -> tuple[int, dict]:
    from pydantic import ValidationError

    from .api import evaluate_scenario
    from .models import OptimizationPolicy
    from .optimizer import OptimizationLimitError
    from .verification import verify_decision_receipt

    try:
        data = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        check_json_shape(data)
        if not isinstance(data, dict):
            return 400, {"error": "Request JSON must be an object.", "code": "invalid_json"}
        if operation == "evaluate":
            if set(data) - {"scenario", "policy"}:
                return 400, {"error": "Unknown request fields.", "code": "invalid_request"}
            scenario = validate_public_scenario(data.get("scenario"))
            policy = OptimizationPolicy.model_validate(data["policy"]) if data.get("policy") is not None else None
            return 200, evaluate_scenario(scenario, policy)
        if operation == "verify":
            receipt = data.get("receipt", data)
            if not isinstance(receipt, dict):
                return 400, {"error": "Receipt must be a JSON object.", "code": "invalid_request"}
            payload = receipt.get("payload")
            if isinstance(payload, dict) and "scenario" in payload:
                validate_public_scenario(payload["scenario"])
            return 200, verify_decision_receipt(receipt).model_dump(mode="json")
        return 404, {"error": "Unknown operation.", "code": "not_found"}
    except PublicLimitError as error:
        return 422, {"error": str(error), "code": "public_limit_exceeded"}
    except OptimizationLimitError:
        return 422, {"error": "Exact search exceeds the declared candidate limit.", "code": "search_limit_exceeded"}
    except ValidationError as error:
        # Do not echo submitted values, exception contexts, or internal paths.
        return 422, {
            "error": "Scenario or policy validation failed.", "code": "validation_failed",
            "details": [{"location": list(item["loc"]), "type": item["type"]}
                        for item in error.errors(include_input=False, include_context=False)[:16]],
        }
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        return 400, {"error": "Invalid JSON.", "code": "invalid_json"}
    except ValueError:
        return 422, {"error": "Input violates the supported model contract.", "code": "invalid_input"}


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not permitted.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Non-finite JSON numbers are not permitted.")


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 1))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    try:
        status, body = execute(sys.argv[1], sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        if len(encoded) > MAX_RESPONSE_BYTES:
            status, encoded = 422, b'{"error":"Result exceeds the public response limit.","code":"public_limit_exceeded"}'
    except MemoryError:
        status, encoded = 422, b'{"error":"Computation exceeded the memory limit.","code":"execution_limit_exceeded"}'
    except Exception:
        status, encoded = 500, b'{"error":"Computation failed.","code":"internal_error"}'
    sys.stdout.buffer.write(str(status).encode() + b"\n" + encoded)


if __name__ == "__main__":
    main()
