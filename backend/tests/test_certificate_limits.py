"""Production-process checks at representative public-envelope corners."""
from __future__ import annotations

import json
import time
import unittest

from engine.public_app import run_computation
from engine.public_limits import MAX_RESPONSE_BYTES, PublicLimitError, validate_public_scenario


def supported_corner(*, dense=False, long_names=False):
    """Near work cap with 4 actions/16 subsets, or 128-edge/Unicode response pressure."""
    services = ["power", "water", "air", "medical"]
    buffer = dict(unit="reserve", capacity_units=0, initial_units=0,
                  depletion_units_per_minute=0, recovery_units_per_minute=0)
    # Long identifiers also exercise generated assignment identifiers and result size.
    name = lambda value: value + "界" * (128 - len(value)) if long_names else value
    assets, resources = [], []
    sources = {}
    for service in services:
        sources[service] = []
        for index in range(3 if dense else 1):
            ident = name(f"{service}-source-{index}")
            sources[service].append(ident)
            assets.append(dict(id=ident, name=ident, kind="source", provides=service,
                               dependency_groups=[], buffer=buffer))
    targets = []
    if dense:
        for index in range(12):
            ident = name(f"endpoint-{index}")
            targets.append(ident)
            assets.append(dict(id=ident, name=ident, kind="facility", provides="medical",
                dependency_groups=[dict(id=name(f"input-{index}-{service}"), service_type=service,
                    provider_asset_ids=sources[service][:3 if index < 8 else 2]) for service in services], buffer=buffer))
    else:
        for service in services:
            routes = []
            for index in range(3):
                ident = name(f"{service}-endpoint-{index}")
                targets.append(ident)
                assets.append(dict(id=ident, name=ident, kind="facility", provides="medical",
                    dependency_groups=[dict(id=name(f"input-{service}-{index}"), service_type=service,
                                           provider_asset_ids=sources[service])], buffer=buffer))
                routes.append(dict(asset_id=ident, travel_minutes=0, setup_minutes=0))
            resources.append(dict(id=name(f"{service}-crew"), name=name(f"{service}-crew"), capabilities=[service], travel_times=routes))
        for index in range(8):
            ident = name(f"unused-{index}")
            assets.append(dict(id=ident, name=ident, kind="source", provides="medical", dependency_groups=[], buffer=buffer))
    return dict(id="certificate-public-corner", horizon_minutes=60 if dense else 47,
        assets=assets, resources=resources, interventions=[],
        faults=[dict(id=name(f"fault-{index}"), asset_id=ident, start_minute=0, end_minute=None)
                for index, ident in enumerate(ident for values in sources.values() for ident in values)],
        demands=[dict(id=name(f"need-{index}"), community_id=name(f"community-{index}"), served_by_asset_id=targets[index % len(targets)],
                      service_type="medical", population=1_000_000, priority_weight=1_000_000) for index in range(32)])


class CertificatePublicLimitsTests(unittest.TestCase):
    def test_near_work_cap_and_dense_response_finish_inside_real_process_limits(self):
        for dense, long_names in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(dense=dense, long_names=long_names):
                scenario = supported_corner(dense=dense, long_names=long_names)
                validate_public_scenario(scenario)
                started = time.perf_counter()
                status, raw = run_computation("evaluate", json.dumps({"scenario": scenario}, ensure_ascii=False).encode())
                self.assertLessEqual(len(raw), MAX_RESPONSE_BYTES)
                result = json.loads(raw)
                if long_names:
                    self.assertEqual(status, 422, raw[:400])
                    self.assertEqual(result["code"], "public_limit_exceeded")
                    self.assertNotIn("coordination_certificate", result)
                    print(f"[certificate boundary] dense={dense}, long identifiers: bounded response rejection in {time.perf_counter()-started:.3f}s")
                    continue
                self.assertEqual(status, 200, raw[:400])
                self.assertEqual(result["coordination_verification"]["status"], "passed")
                self.assertEqual(len(result["coordination_certificate"]["subset_scores"]), 1 if dense else 16)
                self.assertEqual(result["optimization"]["candidate_plans"], 1 if dense else 256)
                print(f"[certificate boundary] dense={dense}, wall={time.perf_counter()-started:.3f}s, bytes={len(raw)}")
        # 256 × 49 × (24 assets + 12 groups + 12 edges + 32 demands) exceeds 1M.
        oversized = supported_corner()
        oversized["horizon_minutes"] = 48
        with self.assertRaises(PublicLimitError):
            validate_public_scenario(oversized)
