import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./api";
import type { Evaluation, Scenario, ScenarioChoice, VerificationReport } from "./types";

vi.mock("./api", () => ({
  api: {
    scenarios: vi.fn(),
    scenario: vi.fn(),
    evaluate: vi.fn(),
    verify: vi.fn(),
  },
}));

const scenario: Scenario = {
  id: "demo",
  horizon_minutes: 2,
  assets: [
    {
      id: "grid",
      name: "Grid feeder",
      kind: "source",
      provides: "power",
      dependency_groups: [],
      buffer: { unit: "reserve_unit", capacity_units: 0, initial_units: 0, depletion_units_per_minute: 0, recovery_units_per_minute: 0 },
    },
    {
      id: "pump",
      name: "Water pump",
      kind: "facility",
      provides: "water",
      dependency_groups: [{ id: "pump-power", service_type: "power", provider_asset_ids: ["grid"] }],
      buffer: { unit: "reserve_unit", capacity_units: 0, initial_units: 0, depletion_units_per_minute: 0, recovery_units_per_minute: 0 },
    },
  ],
  demands: [{ id: "water-need", community_id: "deep-sector", served_by_asset_id: "pump", service_type: "water", population: 10, priority_weight: 1 }],
  faults: [{ id: "grid-down", asset_id: "grid", start_minute: 0, end_minute: null }],
  resources: [{ id: "generator", name: "Generator crew", capabilities: ["power"], travel_times: [{ asset_id: "pump", travel_minutes: 0, setup_minutes: 0 }] }],
  interventions: [],
};

const metric = {
  demand_id: "water-need",
  community_id: "deep-sector",
  service_type: "water",
  population: 10,
  served_minutes: 2,
  service_person_minutes: 20,
  total_service_person_minutes: 20,
  coverage_parts_per_million: 1_000_000,
  priority_weight: 1,
  weighted_service_person_minutes: 20,
};

const plan = {
  plan_id: "plan",
  interventions: [{ id: "assign", resource_id: "generator", target_asset_id: "pump", dependency_group_id: "pump-power", dispatch_minute: 0, duration_minutes: null }],
  idle_resource_ids: [],
  objective: { weighted_service_person_minutes: 20, minimum_community_service_coverage_ppm: 1_000_000, deployment_minutes: 0, intervention_count: 1 },
  demand_metrics: [metric],
  community_service_coverages: [{ demand_id: "water-need", community_id: "deep-sector", service_type: "water", coverage_parts_per_million: 1_000_000 }],
};

const step = (minute: number, available: boolean) => ({
  minute,
  assets: [
    { asset_id: "grid", service_available: false, physical_fault_active: true, unsatisfied_dependency_group_ids: [], buffer_units: 0 },
    { asset_id: "pump", service_available: available, physical_fault_active: false, unsatisfied_dependency_group_ids: available ? [] : ["pump-power"], buffer_units: 0 },
  ],
  active_fault_ids: ["grid-down"],
  active_intervention_ids: available ? ["assign"] : [],
});

const choices: ScenarioChoice[] = [
  { key: "coupled-utility", name: "Coupled utility failure", description: "Two crews restore shared service." },
];

const evaluation: Evaluation = {
  scenario,
  no_intervention_simulation: {
    steps: [step(0, false), step(1, false), step(2, false)],
    demand_metrics: [{ ...metric, served_minutes: 0, service_person_minutes: 0, coverage_parts_per_million: 0, weighted_service_person_minutes: 0 }],
    total_weighted_service_person_minutes: 0,
  },
  optimization: {
    candidate_plans: 2,
    feasible_plans: 2,
    plans_evaluated: 2,
    fairness_eligible_plans: 1,
    exhaustive_search_complete: true,
    best_primary_score: 20,
    selected_plan: plan,
    baseline_comparisons: [
      { baseline: "no_intervention", plan: { ...plan, interventions: [], objective: { ...plan.objective, weighted_service_person_minutes: 0 }, demand_metrics: [] }, primary_score_delta: 20, minimum_community_service_coverage_delta_ppm: 1_000_000 },
      { baseline: "static_priority", plan: { ...plan, objective: { ...plan.objective, weighted_service_person_minutes: 20 } }, primary_score_delta: 0, minimum_community_service_coverage_delta_ppm: 0 },
      { baseline: "greedy", plan: { ...plan, objective: { ...plan.objective, weighted_service_person_minutes: 20 } }, primary_score_delta: 0, minimum_community_service_coverage_delta_ppm: 0 },
    ],
    computation_time_ns: 1000,
  },
  receipt: {
    payload: {
      scenario,
      recommended_plan: plan,
      selected_trace: [step(0, true), step(1, true), step(2, true)],
      search: { candidate_plans: 2, feasible_plans: 2, plans_evaluated: 2, exhaustive_search_complete: true, best_primary_score: 20, selected_primary_score: 20, selected_primary_score_loss: 0, fairness_tradeoff_applied: false },
      assumptions: ["Synthetic deterministic model."],
      limitations: ["Not an operational recommendation."],
    },
    integrity: { algorithm: "sha256", digest: "a".repeat(64) },
    execution_metadata: { exact_search_duration_ns: 1000 },
  },
  traces: {
    no_intervention: [step(0, false), step(1, false), step(2, false)],
    static_priority: [step(0, true), step(1, true), step(2, true)],
    greedy: [step(0, true), step(1, true), step(2, true)],
    optimized: [step(0, true), step(1, true), step(2, true)],
  },
};

const verified: VerificationReport = {
  valid: true,
  schema_status: "passed",
  version_status: "passed",
  integrity_status: "passed",
  input_status: "passed",
  replay_status: "passed",
  baseline_status: "passed",
  optimality_status: "passed",
  verified_payload_sha256: "a".repeat(64),
  verification_duration_ns: 2000,
  issues: [],
};

describe("LIFELINE incident experience", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.scenarios).mockResolvedValue(choices);
    vi.mocked(api.scenario).mockResolvedValue(scenario);
    vi.mocked(api.evaluate).mockResolvedValue(evaluation);
    vi.mocked(api.verify).mockResolvedValue(verified);
  });

  it("shows backend outcomes, permits resource changes, and requests actual receipt verification", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Water pump")).toBeInTheDocument();
    expect(screen.getByText("WEIGHTED SERVICE-PERSON-MINUTES").parentElement).toHaveTextContent("20");
    expect(screen.getByRole("img", { name: /dependency graph at minute 0/i })).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Generator crew available" }));
    await user.click(screen.getByRole("button", { name: "Apply changes & recompute" }));
    await waitFor(() => expect(api.evaluate).toHaveBeenCalledTimes(2));
    const changedScenario = vi.mocked(api.evaluate).mock.calls[1][0];
    expect(changedScenario.resources).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Verify this decision" }));
    expect(await screen.findByText("Receipt verified")).toBeInTheDocument();
    expect(api.verify).toHaveBeenCalledWith(evaluation.receipt);
  });

  it("updates the dependency map with the selected replay policy", async () => {
    render(<App />);
    await screen.findByText("Water pump");
    fireEvent.change(screen.getByLabelText("SHOWING"), { target: { value: "no_intervention" } });
    expect(screen.getByRole("img", { name: /dependency graph at minute 0/i })).toBeInTheDocument();
    expect(screen.getByText("LIFELINE exact")).toBeInTheDocument();
  });
});
