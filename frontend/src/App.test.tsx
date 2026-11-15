import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App, { layoutAssets, relatedAssets } from "./App";
import { api } from "./api";
import type {
  Asset,
  Evaluation,
  Scenario,
  ScenarioChoice,
  VerificationReport,
} from "./types";

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
      buffer: {
        unit: "reserve_unit",
        capacity_units: 0,
        initial_units: 0,
        depletion_units_per_minute: 0,
        recovery_units_per_minute: 0,
      },
    },
    {
      id: "pump",
      name: "Water pump",
      kind: "facility",
      provides: "water",
      dependency_groups: [
        {
          id: "pump-power",
          service_type: "power",
          provider_asset_ids: ["grid"],
        },
      ],
      buffer: {
        unit: "reserve_unit",
        capacity_units: 0,
        initial_units: 0,
        depletion_units_per_minute: 0,
        recovery_units_per_minute: 0,
      },
    },
  ],
  demands: [
    {
      id: "water-need",
      community_id: "deep-sector",
      served_by_asset_id: "pump",
      service_type: "water",
      population: 10,
      priority_weight: 1,
    },
  ],
  faults: [
    { id: "grid-down", asset_id: "grid", start_minute: 0, end_minute: null },
  ],
  resources: [
    {
      id: "generator",
      name: "Generator crew",
      capabilities: ["power"],
      travel_times: [{ asset_id: "pump", travel_minutes: 0, setup_minutes: 0 }],
    },
  ],
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
const baselineMetric = {
  ...metric,
  served_minutes: 1,
  service_person_minutes: 10,
  coverage_parts_per_million: 500_000,
  weighted_service_person_minutes: 10,
};

const plan = {
  plan_id: "plan",
  interventions: [
    {
      id: "assign",
      resource_id: "generator",
      target_asset_id: "pump",
      dependency_group_id: "pump-power",
      dispatch_minute: 0,
      duration_minutes: null,
    },
  ],
  idle_resource_ids: [],
  objective: {
    weighted_service_person_minutes: 20,
    minimum_community_service_coverage_ppm: 1_000_000,
    deployment_minutes: 0,
    intervention_count: 1,
  },
  demand_metrics: [metric],
  community_service_coverages: [
    {
      demand_id: "water-need",
      community_id: "deep-sector",
      service_type: "water",
      coverage_parts_per_million: 1_000_000,
    },
  ],
};
const baselinePlan = {
  ...plan,
  objective: {
    ...plan.objective,
    weighted_service_person_minutes: 10,
    minimum_community_service_coverage_ppm: 500_000,
  },
  demand_metrics: [baselineMetric],
  community_service_coverages: [
    {
      demand_id: "water-need",
      community_id: "deep-sector",
      service_type: "water",
      coverage_parts_per_million: 500_000,
    },
  ],
};

const step = (minute: number, available: boolean) => ({
  minute,
  assets: [
    {
      asset_id: "grid",
      service_available: false,
      physical_fault_active: true,
      unsatisfied_dependency_group_ids: [],
      buffer_units: 0,
    },
    {
      asset_id: "pump",
      service_available: available,
      physical_fault_active: false,
      unsatisfied_dependency_group_ids: available ? [] : ["pump-power"],
      buffer_units: 0,
    },
  ],
  active_fault_ids: ["grid-down"],
  active_intervention_ids: available ? ["assign"] : [],
});

const choices: ScenarioChoice[] = [
  {
    key: "coupled-utility",
    name: "Coupled utility failure",
    description: "Two crews restore shared service.",
  },
];

const evaluation: Evaluation = {
  scenario,
  no_intervention_simulation: {
    steps: [step(0, false), step(1, false), step(2, false)],
    demand_metrics: [
      {
        ...metric,
        served_minutes: 0,
        service_person_minutes: 0,
        coverage_parts_per_million: 0,
        weighted_service_person_minutes: 0,
      },
    ],
    total_weighted_service_person_minutes: 0,
  },
  optimization: {
    policy: { primary_tolerance_ppm: 0 },
    candidate_plans: 2,
    feasible_plans: 2,
    plans_evaluated: 2,
    fairness_eligible_plans: 1,
    exhaustive_search_complete: true,
    best_primary_score: 20,
    selected_plan: plan,
    baseline_comparisons: [
      {
        baseline: "no_intervention",
        plan: {
          ...plan,
          interventions: [],
          objective: { ...plan.objective, weighted_service_person_minutes: 0 },
          demand_metrics: [],
        },
        primary_score_delta: 20,
        minimum_community_service_coverage_delta_ppm: 1_000_000,
      },
      {
        baseline: "static_priority",
        plan: baselinePlan,
        primary_score_delta: 10,
        minimum_community_service_coverage_delta_ppm: 500_000,
      },
      {
        baseline: "greedy",
        plan: baselinePlan,
        primary_score_delta: 10,
        minimum_community_service_coverage_delta_ppm: 500_000,
      },
    ],
    computation_time_ns: 1000,
  },
  receipt: {
    payload: {
      scenario,
      recommended_plan: plan,
      selected_trace: [step(0, true), step(1, true), step(2, true)],
      search: {
        candidate_plans: 2,
        feasible_plans: 2,
        plans_evaluated: 2,
        exhaustive_search_complete: true,
        best_primary_score: 20,
        selected_primary_score: 20,
        selected_primary_score_loss: 0,
        fairness_tradeoff_applied: false,
      },
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

  it("marks edited inputs stale, recomputes them, and verifies the returned receipt", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(
      await screen.findByRole("radio", { name: /Recommended/ }),
    ).toBeInTheDocument();
    expect(
      screen
        .getByText("weighted service-person-minutes")
        .closest(".score-line"),
    ).toHaveTextContent("20");
    expect(
      screen.getByText(
        /Modeled service delivery for water is higher than in the static-priority and greedy plans/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", {
        name: /graph for Recommended response at minute 0/i,
      }),
    ).toBeInTheDocument();
    expect(api.evaluate).toHaveBeenCalledTimes(1);

    await user.click(screen.getByText("Change response conditions"));
    await user.click(
      screen.getByRole("checkbox", { name: "Generator crew available" }),
    );
    expect(screen.getByText("Inputs have changed")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Verify this decision" }),
    ).toBeDisabled();
    expect(api.evaluate).toHaveBeenCalledTimes(1);
    expect(api.verify).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Review changes" }));
    expect(api.evaluate).toHaveBeenCalledTimes(1);
    await user.click(
      screen.getByRole("button", { name: "Confirm and recompute" }),
    );
    await waitFor(() => expect(api.evaluate).toHaveBeenCalledTimes(2));
    const changedScenario = vi.mocked(api.evaluate).mock.calls[1][0];
    expect(changedScenario.resources).toHaveLength(0);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Verify this decision" }),
      ).toBeEnabled(),
    );
    await user.click(
      screen.getByRole("button", { name: "Verify this decision" }),
    );
    expect(await screen.findByText("Receipt verified")).toBeInTheDocument();
    expect(api.verify).toHaveBeenCalledWith(evaluation.receipt);
  });

  it("labels a bounded search as non-exhaustive throughout the interface", async () => {
    const boundedEvaluation: Evaluation = {
      ...evaluation,
      optimization: {
        ...evaluation.optimization,
        exhaustive_search_complete: false,
      },
      receipt: {
        ...evaluation.receipt,
        payload: {
          ...evaluation.receipt.payload,
          search: {
            ...evaluation.receipt.payload.search,
            exhaustive_search_complete: false,
          },
        },
      },
    };
    vi.mocked(api.evaluate).mockResolvedValue(boundedEvaluation);
    render(<App />);

    expect(
      await screen.findByRole("radio", { name: /Recommended/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("Search incomplete")).toBeInTheDocument();
    expect(screen.getByText("Search").parentElement).toHaveTextContent(
      "bound reached",
    );
    expect(screen.queryByText("EXACT")).not.toBeInTheDocument();
  });

  it("switches the graph and timeline to the selected plan trace", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });
    expect(screen.getByText("Generator crew arrives")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /^No response/ }));
    expect(
      screen.getByRole("group", { name: /graph for No response at minute 0/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Generator crew arrives"),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /Recommended/ }));
    expect(
      screen.getByRole("group", {
        name: /graph for Recommended response at minute 0/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Generator crew arrives")).toBeInTheDocument();
  });

  it("shows invalid verification results from the backend", async () => {
    const user = userEvent.setup();
    vi.mocked(api.verify).mockResolvedValue({
      ...verified,
      valid: false,
      integrity_status: "failed",
      issues: [
        {
          code: "DIGEST_MISMATCH",
          category: "integrity",
          message: "Digest mismatch.",
        },
      ],
    });
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });

    await user.click(
      screen.getByRole("button", { name: "Verify this decision" }),
    );

    expect(
      await screen.findByText("Verification found issues"),
    ).toBeInTheDocument();
    expect(screen.getByText(/DIGEST_MISMATCH/)).toBeInTheDocument();
  });

  it("keeps the previous receipt stale and reports a failed recomputation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.evaluate)
      .mockResolvedValueOnce(evaluation)
      .mockRejectedValueOnce(new Error("The API is unavailable."));
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });

    await user.click(screen.getByText("Change response conditions"));
    await user.click(
      screen.getByRole("checkbox", { name: "Generator crew available" }),
    );
    await user.click(screen.getByRole("button", { name: "Review changes" }));
    expect(api.evaluate).toHaveBeenCalledTimes(1);
    await user.click(
      screen.getByRole("button", { name: "Confirm and recompute" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The API is unavailable.",
    );
    expect(screen.getByText("Inputs have changed")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Verify this decision" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry evaluation" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Review response changes");
    expect(api.evaluate).toHaveBeenCalledTimes(2);
  });

  it("keeps keyboard focus in a predictable order across primary controls", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });

    for (const name of [
      "LIFELINE home",
      "Explore",
      "Response",
      "Decision audit",
    ]) {
      await user.tab();
      expect(screen.getByRole("link", { name })).toHaveFocus();
    }
    await user.tab();
    expect(screen.getByLabelText(/active scenario/i)).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("radio", { name: /Recommended/ })).toHaveFocus();
  });
  it("stops replay at the final boundary instead of silently returning to the failure", async () => {
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });
    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", { name: "Play replay" }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3 * 850);
      });
      expect(
        screen.getByRole("button", { name: "Play replay" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("slider", { name: "Simulation minute" }),
      ).toHaveValue("2");
    } finally {
      vi.useRealTimers();
    }
  });

  it("lets a user cancel important input changes without recomputing", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });
    await user.click(screen.getByText("Change response conditions"));
    await user.click(
      screen.getByRole("checkbox", { name: "Generator crew available" }),
    );
    await user.click(screen.getByRole("button", { name: "Review changes" }));
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Generator crew: available → unavailable",
    );
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.evaluate).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "Verify this decision" }),
    ).toBeDisabled();
  });

  it("links keyboard asset selection to providers and community consequences", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });
    const asset = screen.getByRole("button", { name: /^Water pump:/ });
    asset.focus();
    await user.keyboard("{Enter}");
    expect(asset).toHaveAttribute("aria-pressed", "true");
    const inspector = screen.getByRole("complementary", {
      name: "Selected infrastructure",
    });
    expect(
      within(inspector).getByRole("button", { name: "Grid feeder" }),
    ).toBeInTheDocument();
    expect(inspector).toHaveTextContent("deep sector (water)");
    await user.click(
      screen.getByRole("button", { name: "Clear asset selection" }),
    );
    expect(asset).toHaveAttribute("aria-pressed", "false");
  });

  it("updates per-minute community status and radio navigation from backend traces", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });
    expect(
      screen.getByRole("button", { name: /deep sector water · available/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /^No response/ }));
    expect(
      screen.getByRole("button", { name: /deep sector water · unavailable/i }),
    ).toBeInTheDocument();
    await user.keyboard("{ArrowRight}");
    expect(
      screen.getByRole("radio", { name: /^Static priority/ }),
    ).toBeChecked();
    expect(
      screen.getByRole("group", { name: /graph for Static priority/ }),
    ).toBeInTheDocument();
    expect(api.evaluate).toHaveBeenCalledTimes(1);
  });

  it("keeps evaluated routes visible during edits and an unresolved recomputation", async () => {
    const user = userEvent.setup();
    let complete!: (value: Evaluation) => void;
    vi.mocked(api.evaluate)
      .mockResolvedValueOnce(evaluation)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            complete = resolve;
          }),
      );
    render(<App />);
    await screen.findByRole("radio", { name: /Recommended/ });
    await user.click(screen.getByText("Change response conditions"));
    await user.type(
      screen.getByRole("spinbutton", {
        name: "Generator crew travel minutes to pump",
      }),
      "1",
    );
    expect(
      screen.getByRole("button", { name: /Minute 0 Generator crew arrives/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review changes" }));
    await user.click(
      screen.getByRole("button", { name: "Confirm and recompute" }),
    );
    expect(screen.getByRole("radio", { name: /Recommended/ })).toBeChecked();
    expect(
      screen.getByRole("button", { name: /Minute 0 Generator crew arrives/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Verify this decision" }),
    ).toBeDisabled();
    await act(async () => complete(evaluation));
  });
});

describe("responsive dependency map layout", () => {
  const assets: Asset[] = Array.from({ length: 6 }, (_, index) => ({
    id: `asset-${index}`,
    name: `Infrastructure asset ${index + 1}`,
    kind: index === 0 ? "source" : "facility",
    provides: "power",
    dependency_groups:
      index === 0
        ? []
        : [
            {
              id: `input-${index}`,
              service_type: "power",
              provider_asset_ids: [`asset-${index - 1}`],
            },
          ],
    buffer: scenario.assets[0].buffer,
  }));

  it.each([
    [360, "vertical"],
    [900, "vertical"],
    [1400, "horizontal"],
  ] as const)("fits every asset in a %spx viewport", (width, orientation) => {
    const layout = layoutAssets(assets, width);

    expect(layout.orientation).toBe(orientation);
    expect(layout.positions.size).toBe(assets.length);
    for (const asset of assets) {
      const position = layout.positions.get(asset.id);
      expect(position).toBeDefined();
      expect(position!.x - layout.nodeWidth / 2).toBeGreaterThanOrEqual(0);
      expect(position!.x + layout.nodeWidth / 2).toBeLessThanOrEqual(width);
      expect(position!.y - layout.nodeHeight / 2).toBeGreaterThanOrEqual(0);
      expect(position!.y + layout.nodeHeight / 2).toBeLessThanOrEqual(
        layout.height,
      );
    }
  });
});

describe("linked asset traversal", () => {
  it("includes ancestors and consequences but excludes unrelated siblings", () => {
    const branch: Asset = {
      ...scenario.assets[1],
      id: "other",
      dependency_groups: [
        {
          id: "other-input",
          service_type: "power",
          provider_asset_ids: ["grid"],
        },
      ],
    };
    expect(
      [...relatedAssets([...scenario.assets, branch], "pump")].sort(),
    ).toEqual(["grid", "pump"]);
  });
});
