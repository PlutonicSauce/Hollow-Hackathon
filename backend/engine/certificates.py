"""Coordination Certificates: replay-checkable evidence about why a plan works.

A certificate answers questions the optimizer's score alone cannot:

* Do the recommended actions need each other (joint gain)?
* Would removing any single action break the outcome (necessity)?
* Which inclusion-minimal subsets match each demand’s served-minute total?
* Does the greedy policy get stuck before it reaches this plan (trap witness)?

Every number comes from the existing simulator replaying a subset of the
recommended actions. Nothing here calls the optimizer, and nothing changes
simulation, optimization, receipt, or verification semantics. The certificate
is a separate artifact, so existing receipts keep verifying unchanged.

Established ideas, not new math: the joint gain is the Harsanyi dividend (the
top-order interaction term from cooperative game theory), necessity is
score loss under action removal, and sufficient sets are inclusion-minimal
within the recommended action set. The contribution is packaging them as a hash-sealed, replayable
claim over an AND/OR infrastructure model.

Scope limits (stated in the certificate itself): claims hold only inside the
declared deterministic model, minimality is relative to the recommended
action set, and a SHA-256 digest is integrity, not an identity signature.
"""

from __future__ import annotations

import hashlib
import json
from itertools import combinations
from typing import Annotated, Any, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, ValidationError

from .models import Contract, Intervention, NonEmptyString, Scenario
from .simulation import simulate

CERTIFICATE_VERSION = "coordination-certificate-v1"
_PPM = 1_000_000
MAX_CERTIFICATE_ACTIONS = 4  # At most 16 subset replays, matching public resource admission.
Digest = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]

Kind = Literal["no_actions", "single_action", "complementary", "additive", "overlapping", "higher_order"]


class ActionRef(Contract):
    intervention_id: NonEmptyString
    resource_id: NonEmptyString
    target_asset_id: NonEmptyString
    dependency_group_id: NonEmptyString


class DemandServed(Contract):
    demand_id: NonEmptyString
    served_minutes: StrictInt


class AssetAvailability(Contract):
    """Availability at every boundary 0..H; the final boundary earns no interval."""

    asset_id: NonEmptyString
    service_available: tuple[StrictBool, ...]


class SubsetScore(Contract):
    """Simulator outcome when only these actions of the plan are applied."""

    intervention_ids: tuple[str, ...]
    weighted_service_person_minutes: StrictInt
    served: tuple[DemandServed, ...]
    availability: tuple[AssetAvailability, ...]


class ActionNecessity(Contract):
    intervention_id: NonEmptyString
    score_without: StrictInt
    loss_without: StrictInt
    necessary: StrictBool


class DemandSufficiency(Contract):
    """Inclusion-minimal subsets matching the plan's served-minute totals for a demand."""

    demand_id: NonEmptyString
    required_served_minutes: StrictInt
    minimal_sets: tuple[tuple[str, ...], ...]


class GreedyStep(Contract):
    intervention_id: NonEmptyString
    score_after: StrictInt
    marginal_gain: StrictInt


class GreedyWitness(Contract):
    steps: tuple[GreedyStep, ...]
    final_score: StrictInt
    shortfall_versus_plan: StrictInt
    trap_detected: StrictBool


class CertificateLimitations(Contract):
    statements: tuple[str, ...]


class CoordinationCertificate(Contract):
    version: Literal["coordination-certificate-v1"] = CERTIFICATE_VERSION
    scenario_id: NonEmptyString
    scenario_sha256: Digest
    actions: tuple[ActionRef, ...]
    plan_score: StrictInt
    empty_score: StrictInt
    kind: Kind
    joint_gain: StrictInt
    joint_gain_share_ppm: StrictInt
    subset_scores: tuple[SubsetScore, ...]
    necessity: tuple[ActionNecessity, ...]
    full_recovery_minimal_sets: tuple[tuple[str, ...], ...]
    demand_sufficiency: tuple[DemandSufficiency, ...]
    greedy: GreedyWitness
    limitations: CertificateLimitations
    certificate_sha256: Digest


class CertificateCheck(Contract):
    name: NonEmptyString
    passed: StrictBool
    detail: str


class CertificateVerification(Contract):
    status: Literal["passed", "failed"]
    checks: tuple[CertificateCheck, ...]


_LIMITATIONS = (
    "Claims hold inside the declared deterministic LIFELINE model only.",
    "Minimal sets are minimal within the recommended actions, not across all possible plans.",
    "Joint gain of a set larger than two is its Harsanyi dividend, not a pairwise effect.",
    "The digest shows integrity, not authorship or a trusted timestamp.",
    "Scores are weighted service-person-minutes, not people helped or lives saved.",
    "Builder and verifier share the simulator and claim formulas; these checks establish replay consistency, not fully independent verification.",
    "Matching the plan means matching its served-minute totals, not full recovery or the same timing for every demand.",
)


# ---------------------------------------------------------------- hashing


def _canonical(data: Any) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def scenario_sha256(scenario: Scenario) -> str:
    """Digest of the uncommitted scenario inputs a certificate is bound to."""
    return hashlib.sha256(_canonical(scenario.model_dump(mode="json"))).hexdigest()


def _body_digest(certificate: CoordinationCertificate) -> str:
    body = certificate.model_dump(mode="json", exclude={"certificate_sha256"})
    return hashlib.sha256(_canonical(body)).hexdigest()


# ---------------------------------------------------------------- replay


def _with_interventions(
    scenario: Scenario, interventions: tuple[Intervention, ...]
) -> Scenario:
    return Scenario.model_validate(
        {
            "id": scenario.id,
            "horizon_minutes": scenario.horizon_minutes,
            "assets": scenario.assets,
            "demands": scenario.demands,
            "faults": scenario.faults,
            "resources": scenario.resources,
            "interventions": interventions,
        }
    )


def _replay(
    scenario: Scenario, interventions: tuple[Intervention, ...]
) -> SubsetScore:
    result = simulate(_with_interventions(scenario, interventions))
    served = tuple(
        DemandServed(demand_id=metric.demand_id, served_minutes=metric.served_minutes)
        for metric in sorted(result.demand_metrics, key=lambda item: item.demand_id)
    )
    return SubsetScore(
        intervention_ids=tuple(sorted(item.id for item in interventions)),
        weighted_service_person_minutes=result.total_weighted_service_person_minutes,
        served=served,
        availability=tuple(
            AssetAvailability(
                asset_id=asset.id,
                service_available=tuple(
                    next(state.service_available for state in step.assets if state.asset_id == asset.id)
                    for step in result.steps
                ),
            )
            for asset in sorted(scenario.assets, key=lambda item: item.id)
        ),
    )


def _all_subsets(ids: tuple[str, ...]) -> list[tuple[str, ...]]:
    ordered = tuple(sorted(ids))
    subsets: list[tuple[str, ...]] = []
    for size in range(len(ordered) + 1):
        subsets.extend(combinations(ordered, size))
    return subsets


def _score_all_subsets(
    scenario: Scenario, interventions: tuple[Intervention, ...]
) -> dict[tuple[str, ...], SubsetScore]:
    by_id = {item.id: item for item in interventions}
    return {
        subset: _replay(scenario, tuple(by_id[item] for item in subset))
        for subset in _all_subsets(tuple(by_id))
    }


# ---------------------------------------------------------------- claims (pure)


def _joint_gain(
    ids: tuple[str, ...], scores: dict[tuple[str, ...], SubsetScore]
) -> int:
    """Harsanyi dividend of the full set: sum over T of (-1)^(|S|-|T|) v(T)."""
    size = len(ids)
    if size < 2:
        return 0  # a coordination effect needs at least two actions
    return sum(
        (-1) ** (size - len(subset)) * score.weighted_service_person_minutes
        for subset, score in scores.items()
    )


def _kind(count: int, joint_gain: int) -> Kind:
    if count == 0:
        return "no_actions"
    if count == 1:
        return "single_action"
    if count > 2:
        return "higher_order"  # A zero top-order term does not establish global additivity.
    if joint_gain > 0:
        return "complementary"
    if joint_gain == 0:
        return "additive"
    return "overlapping"


def _served(score: SubsetScore, demand_id: str) -> int:
    return next(item.served_minutes for item in score.served if item.demand_id == demand_id)


def _minimal(subsets: list[tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    sets = [frozenset(item) for item in subsets]
    keep = [
        subset
        for subset, as_set in zip(subsets, sets)
        if not any(other < as_set for other in sets)
    ]
    return tuple(sorted(keep, key=lambda item: (len(item), item)))


def _necessity(
    ids: tuple[str, ...], scores: dict[tuple[str, ...], SubsetScore]
) -> tuple[ActionNecessity, ...]:
    full = scores[tuple(sorted(ids))].weighted_service_person_minutes
    rows = []
    for intervention_id in sorted(ids):
        without = tuple(item for item in sorted(ids) if item != intervention_id)
        score = scores[without].weighted_service_person_minutes
        rows.append(
            ActionNecessity(
                intervention_id=intervention_id,
                score_without=score,
                loss_without=full - score,
                necessary=score < full,
            )
        )
    return tuple(rows)


def _sufficiency(
    scenario: Scenario,
    ids: tuple[str, ...],
    scores: dict[tuple[str, ...], SubsetScore],
) -> tuple[tuple[tuple[str, ...], ...], tuple[DemandSufficiency, ...]]:
    full = scores[tuple(sorted(ids))]
    demand_ids = sorted(demand.id for demand in scenario.demands)
    required = {demand_id: _served(full, demand_id) for demand_id in demand_ids}

    per_demand = []
    for demand_id in demand_ids:
        ok = [
            subset
            for subset, score in scores.items()
            if _served(score, demand_id) >= required[demand_id]
        ]
        per_demand.append(
            DemandSufficiency(
                demand_id=demand_id,
                required_served_minutes=required[demand_id],
                minimal_sets=_minimal(ok),
            )
        )
    all_ok = [
        subset
        for subset, score in scores.items()
        if all(_served(score, d) >= required[d] for d in demand_ids)
    ]
    return _minimal(all_ok), tuple(per_demand)


# ---------------------------------------------------------------- greedy witness


def _candidate_interventions(scenario: Scenario) -> list[tuple[tuple[int, str, str, str], Intervention]]:
    """Every one-shot action the optimizer could consider, with a stable order."""
    assets = {asset.id: asset for asset in scenario.assets}
    found: list[tuple[tuple[int, str, str, str], Intervention]] = []
    for resource in sorted(scenario.resources, key=lambda item: item.id):
        routes = {route.asset_id: route for route in resource.travel_times}
        for asset_id in sorted(assets):
            route = routes.get(asset_id)
            if route is None:
                continue
            cost = route.travel_minutes + route.setup_minutes
            if cost >= scenario.horizon_minutes:
                continue
            for group in sorted(assets[asset_id].dependency_groups, key=lambda g: g.id):
                if group.service_type not in resource.capabilities:
                    continue
                identity = json.dumps(
                    [resource.id, asset_id, group.id],
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                found.append(
                    (
                        (cost, resource.id, asset_id, group.id),
                        Intervention(
                            id=f"assignment:{identity}",
                            resource_id=resource.id,
                            target_asset_id=asset_id,
                            dependency_group_id=group.id,
                            dispatch_minute=0,
                        ),
                    )
                )
    return found


def _greedy_witness(scenario: Scenario, plan_score: int) -> GreedyWitness:
    """Replay the greedy policy: repeat the best strictly improving single addition."""
    candidates = _candidate_interventions(scenario)
    chosen: list[Intervention] = []
    used_resources: set[str] = set()
    used_groups: set[str] = set()
    current = _replay(scenario, ()).weighted_service_person_minutes
    steps: list[GreedyStep] = []

    while True:
        best: tuple[tuple[int, str, str, str], Intervention] | None = None
        best_score = current
        for key, action in candidates:
            if (
                action.resource_id in used_resources
                or action.dependency_group_id in used_groups
            ):
                continue
            score = _replay(
                scenario, (*chosen, action)
            ).weighted_service_person_minutes
            if score > best_score or (
                score == best_score
                and score > current
                and best is not None
                and key < best[0]
            ):
                best, best_score = (key, action), score
        if best is None or best_score <= current:
            break
        chosen.append(best[1])
        used_resources.add(best[1].resource_id)
        used_groups.add(best[1].dependency_group_id)
        steps.append(
            GreedyStep(
                intervention_id=best[1].id,
                score_after=best_score,
                marginal_gain=best_score - current,
            )
        )
        current = best_score

    return GreedyWitness(
        steps=tuple(steps),
        final_score=current,
        shortfall_versus_plan=plan_score - current,
        trap_detected=plan_score > current,
    )


# ---------------------------------------------------------------- public API


def _validate_actions(
    scenario: Scenario, interventions: tuple[Intervention, ...]
) -> None:
    if scenario.interventions:
        raise ValueError("certificates require an uncommitted scenario")
    if len(interventions) > MAX_CERTIFICATE_ACTIONS:
        raise ValueError("certificates support at most four recommended actions")
    allowed = {action.id: action for _, action in _candidate_interventions(scenario)}
    for item in interventions:
        if item.id not in allowed or item != allowed[item.id]:
            raise ValueError(f"not an optimizer-style action: {item.id}")
    if len({item.id for item in interventions}) != len(interventions):
        raise ValueError("duplicate action in plan")
    if len({item.resource_id for item in interventions}) != len(interventions):
        raise ValueError("a resource appears more than once")
    if len({item.dependency_group_id for item in interventions}) != len(interventions):
        raise ValueError("a dependency group is covered more than once")


def build_coordination_certificate(
    scenario: Scenario, interventions: tuple[Intervention, ...]
) -> CoordinationCertificate:
    """Build a certificate for a recommended plan using only simulator replays."""
    interventions = tuple(sorted(interventions, key=lambda item: item.id))
    _validate_actions(scenario, interventions)
    ids = tuple(item.id for item in interventions)
    scores = _score_all_subsets(scenario, interventions)

    plan_score = scores[ids].weighted_service_person_minutes
    empty_score = scores[()].weighted_service_person_minutes
    joint = _joint_gain(ids, scores)
    full_sets, per_demand = _sufficiency(scenario, ids, scores)

    draft = CoordinationCertificate(
        scenario_id=scenario.id,
        scenario_sha256=scenario_sha256(scenario),
        actions=tuple(
            ActionRef(
                intervention_id=item.id,
                resource_id=item.resource_id,
                target_asset_id=item.target_asset_id,
                dependency_group_id=item.dependency_group_id,
            )
            for item in interventions
        ),
        plan_score=plan_score,
        empty_score=empty_score,
        kind=_kind(len(ids), joint),
        joint_gain=joint,
        joint_gain_share_ppm=(joint * _PPM // plan_score) if plan_score > 0 else 0,
        subset_scores=tuple(scores[key] for key in sorted(scores, key=lambda s: (len(s), s))),
        necessity=_necessity(ids, scores) if ids else (),
        full_recovery_minimal_sets=full_sets,
        demand_sufficiency=per_demand,
        greedy=_greedy_witness(scenario, plan_score),
        limitations=CertificateLimitations(statements=_LIMITATIONS),
        certificate_sha256="0" * 64,
    )
    return draft.model_copy(update={"certificate_sha256": _body_digest(draft)})


def verify_coordination_certificate(
    scenario: Scenario, certificate: CoordinationCertificate | dict[str, Any]
) -> CertificateVerification:
    """Recheck a certificate against a scenario by replaying the simulator.

    Fails closed: any parse error, wrong binding, or mismatch is reported.
    The production optimizer is never called.
    """
    checks: list[CertificateCheck] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append(CertificateCheck(name=name, passed=passed, detail=detail))

    try:
        cert = CoordinationCertificate.model_validate(
            certificate.model_dump(mode="python", warnings=False)
            if isinstance(certificate, CoordinationCertificate) else certificate
        )
    except ValidationError as error:
        add("schema", False, f"certificate does not match the schema ({error.error_count()} issues)")
        return CertificateVerification(status="failed", checks=tuple(checks))
    add("schema", True, "certificate matches the versioned schema")

    add(
        "payload_integrity",
        _body_digest(cert) == cert.certificate_sha256,
        "recorded SHA-256 matches the canonical certificate body",
    )

    bound = scenario_sha256(scenario) == cert.scenario_sha256 and scenario.id == cert.scenario_id
    add(
        "scenario_binding",
        bound,
        "certificate was made for exactly these scenario inputs"
        if bound
        else "scenario inputs differ from the ones this certificate was made for",
    )
    if not bound:
        return CertificateVerification(status="failed", checks=tuple(checks))

    try:
        if len(cert.actions) > MAX_CERTIFICATE_ACTIONS:
            raise ValueError("certificates support at most four recommended actions")
        by_id = {action.id: action for _, action in _candidate_interventions(scenario)}
        plan = tuple(by_id[item.intervention_id] for item in cert.actions)
        _validate_actions(scenario, plan)
        expected_refs = tuple(
            ActionRef(intervention_id=item.id, resource_id=item.resource_id,
                      target_asset_id=item.target_asset_id, dependency_group_id=item.dependency_group_id)
            for item in sorted(plan, key=lambda item: item.id)
        )
        if cert.actions != expected_refs:
            raise ValueError("action references do not match their canonical assignments")
        add("actions_valid", True, "every action is a feasible one-shot assignment")
    except (KeyError, ValueError) as error:
        add("actions_valid", False, str(error))
        return CertificateVerification(status="failed", checks=tuple(checks))

    ids = tuple(sorted(item.id for item in plan))
    scores = _score_all_subsets(scenario, plan)
    recorded = {item.intervention_ids: item for item in cert.subset_scores}
    add(
        "subset_replay",
        recorded == scores and len(cert.subset_scores) == len(scores),
        f"replayed {len(scores)} action subsets with the simulator",
    )

    joint = _joint_gain(ids, scores)
    plan_score = scores[ids].weighted_service_person_minutes
    add(
        "joint_gain",
        cert.joint_gain == joint
        and cert.kind == _kind(len(ids), joint)
        and cert.plan_score == plan_score
        and cert.empty_score == scores[()].weighted_service_person_minutes
        and cert.joint_gain_share_ppm == ((joint * _PPM // plan_score) if plan_score > 0 else 0),
        "joint gain and plan score recomputed from the replays",
    )
    add(
        "necessity",
        cert.necessity == (_necessity(ids, scores) if ids else ()),
        "each action was removed and the plan replayed",
    )
    full_sets, per_demand = _sufficiency(scenario, ids, scores)
    add(
        "minimal_sufficiency",
        cert.full_recovery_minimal_sets == full_sets and cert.demand_sufficiency == per_demand,
        "minimal sufficient subsets recomputed by exhaustive subset search",
    )
    add(
        "greedy_witness",
        cert.greedy == _greedy_witness(scenario, plan_score),
        "greedy policy replayed step by step on the same simulator",
    )
    add("claim_scope", cert.limitations.statements == _LIMITATIONS,
        "scope and shared-formula limitations match this certificate version")
    status = "passed" if all(check.passed for check in checks) else "failed"
    return CertificateVerification(status=status, checks=tuple(checks))
