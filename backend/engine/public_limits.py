"""Hosting admission limits, separate from versioned model/receipt semantics."""

from __future__ import annotations

import math
from typing import Any

from .models import Scenario

MAX_REQUEST_BYTES = 2_000_000
MAX_RESPONSE_BYTES = 8_000_000
MAX_CANDIDATES = 256
MAX_WORK = 1_000_000
WALL_SECONDS = 8
CPU_SECONDS = 6
MEMORY_BYTES = 256 * 1024 * 1024


class PublicLimitError(ValueError):
    """An otherwise valid input exceeds the public demo's supported envelope."""


def check_json_shape(value: Any) -> None:
    """Bound arbitrary receipt metadata before Pydantic constructs nested models."""
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if count > 60_000 or depth > 32:
            raise PublicLimitError("JSON exceeds 60,000 values or 32 nesting levels.")
        if isinstance(item, dict):
            if len(item) > 256:
                raise PublicLimitError("JSON objects support at most 256 keys.")
            pending.extend((key, depth + 1) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            if len(item) > 4096:
                raise PublicLimitError("JSON arrays support at most 4,096 entries.")
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str) and len(item) > 32_768:
            raise PublicLimitError("JSON strings support at most 32,768 characters.")
        elif isinstance(item, int) and abs(item) > 10**20:
            raise PublicLimitError("JSON integers exceed the supported range.")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Non-finite numbers are not permitted.")


def validate_public_scenario(data: Any) -> Scenario:
    """Reject oversized collections before reference/graph validation."""
    if isinstance(data, dict):
        for name, maximum in (
            ("assets", 24), ("demands", 32), ("faults", 32),
            ("resources", 4), ("interventions", 4),
        ):
            _length(data.get(name), maximum, name)
        for asset in data.get("assets", []) if isinstance(data.get("assets"), list) else []:
            if isinstance(asset, dict):
                _length(asset.get("dependency_groups"), 4, "dependency groups per asset")
                groups = asset.get("dependency_groups", [])
                for group in groups if isinstance(groups, list) else []:
                    if isinstance(group, dict):
                        _length(group.get("provider_asset_ids"), 8, "providers per group")
        resources = data.get("resources", [])
        for resource in resources if isinstance(resources, list) else []:
            if isinstance(resource, dict):
                _length(resource.get("travel_times"), 24, "routes per resource")
                _length(resource.get("capabilities"), 5, "capabilities per resource")
        _check_scenario_scalars(data)

    scenario = Scenario.model_validate(data)
    groups = sum(len(asset.dependency_groups) for asset in scenario.assets)
    edges = sum(len(group.provider_asset_ids) for asset in scenario.assets
                for group in asset.dependency_groups)
    if groups > 64 or edges > 128:
        raise PublicLimitError("Scenario supports at most 64 dependency groups and 128 provider edges.")

    # Count the raw idle-or-assignment space, including conflicting assignments.
    # This is admission control only; verification retains its own enumerator.
    candidates = 1
    for resource in scenario.resources:
        routes = {route.asset_id: route for route in resource.travel_times}
        actions = 0
        for asset in scenario.assets:
            route = routes.get(asset.id)
            if route and route.travel_minutes + route.setup_minutes < scenario.horizon_minutes:
                actions += sum(group.service_type in resource.capabilities
                               for group in asset.dependency_groups)
        candidates *= 1 + actions
        if candidates > MAX_CANDIDATES:
            raise PublicLimitError(f"Public search supports at most {MAX_CANDIDATES} candidate plans.")
    work = candidates * (scenario.horizon_minutes + 1) * (
        len(scenario.assets) + groups + edges + len(scenario.demands)
    )
    if work > MAX_WORK:
        raise PublicLimitError(f"Scenario exceeds the public work budget of {MAX_WORK:,} units.")
    return scenario


def _length(value: Any, maximum: int, name: str) -> None:
    if isinstance(value, list) and len(value) > maximum:
        raise PublicLimitError(f"Public scenarios support at most {maximum} {name}.")


def _check_scenario_scalars(data: dict) -> None:
    pending = [data]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
            horizon = item.get("horizon_minutes")
            if type(horizon) is int and horizon > 60:
                raise PublicLimitError("Public simulation horizon is at most 60 minutes.")
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str) and len(item) > 128:
            raise PublicLimitError("Scenario strings support at most 128 characters.")
        elif type(item) is int and abs(item) > 1_000_000:
            raise PublicLimitError("Scenario integers support magnitudes up to 1,000,000.")
