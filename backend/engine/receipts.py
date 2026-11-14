"""Versioned, replayable decision receipts with deterministic SHA-256 payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import Field, PositiveInt, StrictStr

from .models import (
    BaselineComparison,
    Contract,
    NonEmptyString,
    NonNegativeInt,
    OptimizationPolicy,
    OptimizationResult,
    PlanSummary,
    Scenario,
    TimeStep,
)
from .simulation import simulate

RECEIPT_SCHEMA_VERSION = "1.0"
SIMULATION_MODEL_VERSION = "1.0"
OPTIMIZER_VERSION = "1.0"
CANONICALIZATION_VERSION = "lifeline-json-v1"

Sha256Hex = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class ResourceConstraints(Contract):
    dispatch_minute: NonNegativeInt = 0
    max_assignments_per_resource: PositiveInt = 1
    max_assignments_per_dependency_group: PositiveInt = 1
    idle_resources_allowed: bool = True
    resource_redeployment_allowed: bool = False
    support_duration: Literal["through_scenario_horizon"] = "through_scenario_horizon"


class MetricDefinition(Contract):
    name: NonEmptyString
    unit: NonEmptyString
    formula: NonEmptyString
    interpretation: NonEmptyString


class ReceiptSearchSummary(Contract):
    candidate_plans: NonNegativeInt
    feasible_plans: NonNegativeInt
    plans_evaluated: NonNegativeInt
    fairness_eligible_plans: NonNegativeInt
    exhaustive_search_complete: bool
    best_primary_score: NonNegativeInt
    selected_primary_score: NonNegativeInt
    selected_primary_score_loss: NonNegativeInt
    fairness_tradeoff_applied: bool


class ReceiptPayload(Contract):
    schema_version: NonEmptyString
    canonicalization_version: NonEmptyString
    simulation_model_version: NonEmptyString
    optimizer_version: NonEmptyString
    scenario: dict[str, Any]
    optimization_policy: OptimizationPolicy
    resource_constraints: ResourceConstraints
    recommended_plan: PlanSummary
    selected_trace: tuple[TimeStep, ...]
    search: ReceiptSearchSummary
    baseline_comparisons: tuple[BaselineComparison, ...]
    metric_definitions: tuple[MetricDefinition, ...] = Field(min_length=1)
    assumptions: tuple[NonEmptyString, ...] = Field(min_length=1)
    limitations: tuple[NonEmptyString, ...] = Field(min_length=1)


class ReceiptIntegrity(Contract):
    algorithm: NonEmptyString
    digest: Sha256Hex


class ReceiptExecutionMetadata(Contract):
    exact_search_duration_ns: NonNegativeInt


class DecisionReceipt(Contract):
    payload: ReceiptPayload
    integrity: ReceiptIntegrity
    execution_metadata: ReceiptExecutionMetadata | None = None


RESOURCE_CONSTRAINTS = ResourceConstraints()

METRIC_DEFINITIONS = (
    MetricDefinition(
        name="service_person_minutes",
        unit="person-service-minutes",
        formula="population * served_minutes",
        interpretation=(
            "Service delivered to the demand population; people appearing in "
            "multiple demands are counted once per demand."
        ),
    ),
    MetricDefinition(
        name="weighted_service_person_minutes",
        unit="priority-weighted person-service-minutes",
        formula="service_person_minutes * priority_weight",
        interpretation=(
            "Policy score contribution; priority_weight is an explicit scenario "
            "input, not an empirically calibrated urgency."
        ),
    ),
    MetricDefinition(
        name="coverage_parts_per_million",
        unit="parts per million (ppm)",
        formula=(
            "floor(service_person_minutes * 1_000_000 / "
            "total_service_person_minutes)"
        ),
        interpretation=(
            "Unweighted delivered service divided by possible service for one "
            "explicit demand record."
        ),
    ),
    MetricDefinition(
        name="minimum_community_service_coverage_ppm",
        unit="parts per million (ppm)",
        formula="minimum coverage_parts_per_million across demand records",
        interpretation=(
            "Worst modeled community/service/need coverage; it cannot represent "
            "needs or population subgroups absent from the scenario."
        ),
    ),
    MetricDefinition(
        name="deployment_minutes",
        unit="resource-minutes",
        formula="sum(travel_minutes + setup_minutes) across assigned resources",
        interpretation="Deterministic route and setup cost; not elapsed plan duration.",
    ),
    MetricDefinition(
        name="weighted_service_person_minutes_total",
        unit="priority-weighted person-service-minutes",
        formula=(
            "sum(population * served_minutes * priority_weight across demands)"
        ),
        interpretation="Primary optimization objective; not lives saved.",
    ),
    MetricDefinition(
        name="best_primary_score",
        unit="priority-weighted person-service-minutes",
        formula="maximum weighted_service_person_minutes across feasible plans",
        interpretation="Primary optimum within the exhaustively evaluated action space.",
    ),
    MetricDefinition(
        name="selected_primary_score",
        unit="priority-weighted person-service-minutes",
        formula="recommended_plan.objective.weighted_service_person_minutes",
        interpretation="Selected plan score after configured fairness tie-breaking.",
    ),
    MetricDefinition(
        name="intervention_count",
        unit="assignments",
        formula="count(recommended interventions)",
        interpretation="Final deterministic tie-break after travel and setup cost.",
    ),
    MetricDefinition(
        name="candidate_plans",
        unit="plans",
        formula="product(1 + eligible action count for each resource)",
        interpretation="Raw idle-or-action combinations before conflict rejection.",
    ),
    MetricDefinition(
        name="feasible_plans",
        unit="plans",
        formula="candidate plans with no duplicate dependency-group assignments",
        interpretation="Every feasible plan is evaluated in an exhaustive search.",
    ),
    MetricDefinition(
        name="plans_evaluated",
        unit="plans",
        formula="number of feasible plans simulated by the exact optimizer",
        interpretation="Must equal feasible_plans when exhaustive_search_complete is true.",
    ),
    MetricDefinition(
        name="fairness_eligible_plans",
        unit="plans",
        formula=(
            "plans whose primary score is at least (1 - tolerance_ppm / 1_000_000) "
            "of the best primary score"
        ),
        interpretation="Candidates compared by minimum demand-record coverage.",
    ),
    MetricDefinition(
        name="exhaustive_search_complete",
        unit="boolean",
        formula="true iff every feasible assignment candidate was evaluated",
        interpretation="An incomplete search must never be reported as optimal.",
    ),
    MetricDefinition(
        name="fairness_tradeoff_applied",
        unit="boolean",
        formula="selected_primary_score < best_primary_score",
        interpretation="Indicates a fairness tie-break accepted a lower primary score.",
    ),
    MetricDefinition(
        name="selected_primary_score_loss",
        unit="priority-weighted service-person-minutes",
        formula="best_primary_score - selected_primary_score",
        interpretation="Nonzero only when the fairness tie-break selects a lower primary score.",
    ),
    MetricDefinition(
        name="primary_score_delta",
        unit="priority-weighted service-person-minutes",
        formula="recommended primary score - baseline primary score",
        interpretation="Signed counterfactual difference; zero and negative values are valid.",
    ),
    MetricDefinition(
        name="minimum_community_service_coverage_delta_ppm",
        unit="parts per million (ppm)",
        formula="recommended minimum coverage - baseline minimum coverage",
        interpretation="Signed difference across explicit demand records.",
    ),
    MetricDefinition(
        name="exact_search_duration_ns",
        unit="nanoseconds",
        formula="monotonic-clock duration of candidate generation and exact search",
        interpretation="Execution metadata outside the canonical digest; not a latency promise.",
    ),
    MetricDefinition(
        name="verification_duration_ns",
        unit="nanoseconds",
        formula="monotonic-clock duration of receipt verification",
        interpretation="Verification-report metadata; not part of the receipt payload.",
    ),
)

MODEL_ASSUMPTIONS = (
    "Service availability is binary; dependency groups are ANDed and providers within a group are ORed.",
    "The dependency graph is acyclic and evaluated in stable provider-before-dependent order.",
    "Buffers are asset-specific integer reserve units and are not assumed to represent minutes.",
    "Physical faults suppress asset service and are not repaired by backup-service interventions.",
    "An intervention supplies only its named dependency group after integer travel and setup time.",
    "Each explicit demand is counted independently, including people who appear in multiple service demands.",
    "Priority weights and primary-score fairness tolerance are human-selected policy inputs.",
)

MODEL_LIMITATIONS = (
    "No physical flow, electrical capacity, load, air quality, clinical outcome, or human life is modeled.",
    "No failure uncertainty, resource fuel, resource capacity, redeployment, or real-time data is modeled.",
    "Fairness applies only to the explicit demand records and cannot cover omitted needs or population subgroups.",
    "Optimality is limited to the declared one-shot assignment space and candidate-plan bound.",
)


def canonical_payload_bytes(payload: ReceiptPayload) -> bytes:
    """Serialize the payload using the documented LIFELINE JSON canonicalization."""
    data = payload.model_dump(mode="json")
    canonical = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return canonical.encode("utf-8")


def payload_sha256(payload: ReceiptPayload) -> str:
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def export_receipt_json(receipt: DecisionReceipt) -> str:
    """Export a stable JSON envelope; execution metadata is outside the digest."""
    return json.dumps(
        receipt.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def create_decision_receipt(
    scenario: Scenario,
    result: OptimizationResult,
    *,
    include_execution_metadata: bool = True,
) -> DecisionReceipt:
    if scenario.interventions:
        raise ValueError("receipt scenario must not contain preassigned interventions")

    selected_score = (
        result.selected_plan.objective.weighted_service_person_minutes
    )
    payload = ReceiptPayload(
        schema_version=RECEIPT_SCHEMA_VERSION,
        canonicalization_version=CANONICALIZATION_VERSION,
        simulation_model_version=SIMULATION_MODEL_VERSION,
        optimizer_version=OPTIMIZER_VERSION,
        scenario=scenario.model_dump(mode="json"),
        optimization_policy=result.policy,
        resource_constraints=RESOURCE_CONSTRAINTS,
        recommended_plan=result.selected_plan,
        selected_trace=_selected_plan_trace(scenario, result.selected_plan),
        search=ReceiptSearchSummary(
            candidate_plans=result.candidate_plans,
            feasible_plans=result.feasible_plans,
            plans_evaluated=result.plans_evaluated,
            fairness_eligible_plans=result.fairness_eligible_plans,
            exhaustive_search_complete=result.exhaustive_search_complete,
            best_primary_score=result.best_primary_score,
            selected_primary_score=selected_score,
            selected_primary_score_loss=result.best_primary_score - selected_score,
            fairness_tradeoff_applied=selected_score < result.best_primary_score,
        ),
        baseline_comparisons=result.baseline_comparisons,
        metric_definitions=METRIC_DEFINITIONS,
        assumptions=MODEL_ASSUMPTIONS,
        limitations=MODEL_LIMITATIONS,
    )
    return DecisionReceipt(
        payload=payload,
        integrity=ReceiptIntegrity(
            algorithm="sha256",
            digest=payload_sha256(payload),
        ),
        execution_metadata=(
            ReceiptExecutionMetadata(
                exact_search_duration_ns=result.computation_time_ns
            )
            if include_execution_metadata
            else None
        ),
    )


def _selected_plan_trace(
    scenario: Scenario,
    plan: PlanSummary,
) -> tuple[TimeStep, ...]:
    plan_scenario = Scenario.model_validate(
        {
            "id": scenario.id,
            "horizon_minutes": scenario.horizon_minutes,
            "assets": scenario.assets,
            "demands": scenario.demands,
            "faults": scenario.faults,
            "resources": scenario.resources,
            "interventions": plan.interventions,
        }
    )
    replay = simulate(plan_scenario)
    return replay.steps
