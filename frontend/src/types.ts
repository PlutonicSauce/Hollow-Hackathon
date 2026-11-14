export type DependencyGroup = {
  id: string;
  service_type: string;
  provider_asset_ids: string[];
};

export type Asset = {
  id: string;
  name: string;
  kind: string;
  provides: string;
  dependency_groups: DependencyGroup[];
  buffer: {
    unit: string;
    capacity_units: number;
    initial_units: number;
    depletion_units_per_minute: number;
    recovery_units_per_minute: number;
  };
};

export type Scenario = {
  id: string;
  horizon_minutes: number;
  assets: Asset[];
  demands: Array<{
    id: string;
    community_id: string;
    served_by_asset_id: string;
    service_type: string;
    population: number;
    priority_weight: number;
  }>;
  faults: Array<{
    id: string;
    asset_id: string;
    start_minute: number;
    end_minute: number | null;
  }>;
  resources: Array<{
    id: string;
    name: string;
    capabilities: string[];
    travel_times: Array<{
      asset_id: string;
      travel_minutes: number;
      setup_minutes: number;
    }>;
  }>;
  interventions: unknown[];
};

export type OptimizationPolicy = {
  primary_tolerance_ppm?: number;
  max_candidate_plans?: number;
};

export type AssetState = {
  asset_id: string;
  service_available: boolean;
  physical_fault_active: boolean;
  unsatisfied_dependency_group_ids: string[];
  buffer_units: number;
};

export type TimeStep = {
  minute: number;
  assets: AssetState[];
  active_fault_ids: string[];
  active_intervention_ids: string[];
};

export type DemandMetric = {
  demand_id: string;
  community_id: string;
  service_type: string;
  population: number;
  served_minutes: number;
  service_person_minutes: number;
  total_service_person_minutes: number;
  coverage_parts_per_million: number;
  priority_weight: number;
  weighted_service_person_minutes: number;
};

export type Plan = {
  plan_id: string;
  interventions: Array<{
    id: string;
    resource_id: string;
    target_asset_id: string;
    dependency_group_id: string;
    dispatch_minute: number;
    duration_minutes: number | null;
  }>;
  idle_resource_ids: string[];
  objective: {
    weighted_service_person_minutes: number;
    minimum_community_service_coverage_ppm: number;
    deployment_minutes: number;
    intervention_count: number;
  };
  demand_metrics: DemandMetric[];
  community_service_coverages: Array<{
    demand_id: string;
    community_id: string;
    service_type: string;
    coverage_parts_per_million: number;
  }>;
};

export type Baseline = {
  baseline: "no_intervention" | "static_priority" | "greedy";
  plan: Plan;
  primary_score_delta: number;
  minimum_community_service_coverage_delta_ppm: number;
};

export type OptimizationResult = {
  candidate_plans: number;
  feasible_plans: number;
  plans_evaluated: number;
  fairness_eligible_plans: number;
  exhaustive_search_complete: boolean;
  best_primary_score: number;
  selected_plan: Plan;
  baseline_comparisons: Baseline[];
  computation_time_ns: number;
};

export type Receipt = {
  payload: {
    scenario: Scenario;
    recommended_plan: Plan;
    selected_trace: TimeStep[];
    search: {
      candidate_plans: number;
      feasible_plans: number;
      plans_evaluated: number;
      exhaustive_search_complete: boolean;
      best_primary_score: number;
      selected_primary_score: number;
      selected_primary_score_loss: number;
      fairness_tradeoff_applied: boolean;
    };
    assumptions: string[];
    limitations: string[];
  };
  integrity: {
    algorithm: string;
    digest: string;
  };
  execution_metadata: { exact_search_duration_ns: number } | null;
};

export type Evaluation = {
  scenario: Scenario;
  no_intervention_simulation: {
    steps: TimeStep[];
    demand_metrics: DemandMetric[];
    total_weighted_service_person_minutes: number;
  };
  optimization: OptimizationResult;
  receipt: Receipt;
  traces: Record<string, TimeStep[]>;
};

export type VerificationReport = {
  valid: boolean;
  schema_status: string;
  version_status: string;
  integrity_status: string;
  input_status: string;
  replay_status: string;
  baseline_status: string;
  optimality_status: string;
  verified_payload_sha256: string | null;
  verification_duration_ns: number;
  issues: Array<{ code: string; category: string; message: string }>;
};

export type ScenarioChoice = {
  key: string;
  name: string;
  description: string;
};
