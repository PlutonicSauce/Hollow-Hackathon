"""Deterministic receipt fixtures for examples, tests, and future UI work."""

from .optimizer import optimize_interventions
from .receipts import DecisionReceipt, create_decision_receipt
from .scenarios import signature_scenario


def signature_receipt_fixture() -> DecisionReceipt:
    scenario = signature_scenario()
    result = optimize_interventions(scenario)
    return create_decision_receipt(
        scenario,
        result,
        include_execution_metadata=False,
    )
