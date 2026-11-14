"""
LIFELINE Engine Data Models
Defines core data structures for infrastructure nodes, dependency edges,
resources, simulation states, decision receipts, and benchmark comparisons.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ServiceLayer(str, Enum):
    POWER = "POWER"
    WATER = "WATER"
    AIR = "AIR"
    MEDICAL = "MEDICAL"
    TRANSIT = "TRANSIT"


class CriticalityTier(int, Enum):
    TIER_1_LIFE_CRITICAL = 1   # ICUs, Trauma Centers, Main Air Scrubbers
    TIER_2_ESSENTIAL = 2       # Potable Water Booster Pumps, Power Substations, Main Transit
    TIER_3_SUPPORT = 3         # Administrative Hubs, Storage Warehouses, Secondary Lighting


class ResourceType(str, Enum):
    MOBILE_GENERATOR = "MOBILE_GENERATOR"        # Provides 500kW emergency electrical feed
    WATER_PUMPER_TRUCK = "WATER_PUMPER_TRUCK"    # Injects emergency cooling/potable water
    AIR_SCRUBBER_BYPASS = "AIR_SCRUBBER_BYPASS"  # Portable scrubber cartridge & bypass kit
    MULTI_DISCIPLINE_CREW = "MULTI_DISCIPLINE_CREW"  # Versatile repair and cross-tie crew


class BaselinePolicy(str, Enum):
    FCFS = "FCFS"                              # First-Come, First-Served ticket dispatch
    STATIC_PRIORITY = "STATIC_PRIORITY"        # Highest tier first, ignoring buffers
    DEGREE_CENTRALITY = "DEGREE_CENTRALITY"    # Highest connectivity node first
    LIFELINE_OPTIMAL = "LIFELINE_OPTIMAL"      # Counterfactual buffer-aware optimizer


class NodeCoordinates(BaseModel):
    x: float = Field(..., description="X coordinate in spatial or sector grid (meters)")
    y: float = Field(..., description="Y coordinate in spatial or sector grid (meters)")
    z: float = Field(..., description="Z coordinate or subterranean level depth (meters)")


class InfrastructureNode(BaseModel):
    id: str = Field(..., description="Unique node identifier, e.g. POWER_SUB_04")
    name: str = Field(..., description="Human-readable asset name")
    layer: ServiceLayer = Field(..., description="Infrastructure domain layer")
    tier: CriticalityTier = Field(..., description="Criticality priority tier")
    sector: str = Field(..., description="Geographic or subterranean sector, e.g. Level 12 Deep")
    population: int = Field(default=0, description="Directly dependent human population count")
    
    # Capacity & Buffer Dynamics
    capacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Operational capacity ratio [0=failed, 1=100%]")
    current_buffer: float = Field(..., ge=0.0, description="Current internal buffer reserve (minutes of autonomous survival)")
    max_buffer: float = Field(..., ge=0.0, description="Maximum buffer capacity in minutes")
    decay_rate: float = Field(default=1.0, description="Buffer drain rate per minute when upstream supply is compromised")
    recovery_rate: float = Field(default=1.0, description="Buffer recharge rate per minute when upstream is restored")
    sufficiency_threshold: float = Field(default=0.8, ge=0.0, le=1.0, description="Minimum input capacity needed to prevent buffer decay")
    
    # State flags
    is_failed: bool = Field(default=False, description="Whether the component has experienced an internal root failure")
    is_isolated: bool = Field(default=False, description="Whether the component is physically isolated for repair")
    active_intervention: Optional[str] = Field(default=None, description="ID of resource currently assisting this node")
    
    coords: NodeCoordinates = Field(..., description="Spatial position for transit distance calculation")


class DependencyEdge(BaseModel):
    id: str = Field(..., description="Unique edge identifier")
    source_id: str = Field(..., description="Upstream provider node ID")
    target_id: str = Field(..., description="Downstream dependent node ID")
    layer: ServiceLayer = Field(..., description="Type of service transmitted along edge")
    weight: float = Field(default=1.0, description="Relative dependency weight [0-1]")
    min_required_capacity: float = Field(default=0.8, description="Minimum upstream capacity required for downstream health")
    flow_delay_minutes: int = Field(default=0, description="Time delay for transmission propagation")
    is_severed: bool = Field(default=False, description="Whether the connection line/pipe/duct is physically severed")


class InterventionResource(BaseModel):
    id: str = Field(..., description="Unique resource ID, e.g. CREW_GEN_ALPHA")
    name: str = Field(..., description="Resource display name")
    resource_type: ResourceType = Field(..., description="Type of capability provided")
    base_node_id: str = Field(..., description="Starting station or depot node ID")
    current_node_id: str = Field(..., description="Current location node ID")
    speed_kmh: float = Field(default=40.0, description="Transit speed in transit tunnels (km/h)")
    is_deployed: bool = Field(default=False, description="Whether currently dispatched or committed")
    target_node_id: Optional[str] = Field(default=None, description="Assigned destination node ID")
    dispatch_time_m: Optional[int] = Field(default=None, description="Time minute when dispatch was ordered")
    arrival_time_m: Optional[int] = Field(default=None, description="Time minute when crew arrives at target")
    setup_duration_m: int = Field(default=10, description="Minutes required to connect equipment after arrival")


class FaultEvent(BaseModel):
    time_m: int = Field(..., description="Minute at which the fault occurs")
    target_node_id: str = Field(..., description="Node where the initiating fault strikes")
    failure_type: str = Field(..., description="E.g. EXPLOSION, PIPE_RUPTURE, CONTAMINATION")
    remaining_capacity: float = Field(default=0.0, ge=0.0, le=1.0, description="Post-fault capacity")


class NodeSnapshot(BaseModel):
    node_id: str
    capacity: float
    current_buffer: float
    time_to_cascade_m: float
    is_failed: bool
    status: str  # NOMINAL, BUFFER_DRAINING, CRITICAL_WARNING, CASCADE_FAILED, RECOVERING


class SimulationStep(BaseModel):
    time_m: int
    active_faults: List[str]
    nodes: Dict[str, NodeSnapshot]
    total_life_hours_saved: float
    unserved_population: int
    cascades_active: int
    events_logged: List[str]


class ActionProposal(BaseModel):
    action_id: str
    resource_id: str
    target_node_id: str
    action_type: str
    dispatch_time_m: int
    transit_time_m: int
    arrival_time_m: int
    buffer_headroom_remaining_m: float
    expected_cascades_prevented: List[str]


class RejectedAlternative(BaseModel):
    candidate_node_id: str
    candidate_name: str
    rejection_code: str
    rejection_reason: str
    counterfactual_life_hours: float
    delta_vs_recommended: float


class EquityImpact(BaseModel):
    worst_off_sector: str
    worst_off_deprivation_pct: float
    baseline_worst_off_deprivation_pct: float
    gini_index: float
    atkinson_index: float
    demographic_balance_note: str


class DecisionReceipt(BaseModel):
    receipt_id: str
    timestamp_iso: str
    scenario_seed: int
    incident_trigger: Dict[str, Any]
    policy_name: str
    recommended_action: ActionProposal
    counterfactual_analysis: Dict[str, Any]
    rejected_alternatives: List[RejectedAlternative]
    equity_impact: EquityImpact
    uncertainty_sensitivity: Dict[str, Any]
    audit_hash: str


class PolicyEvaluationResult(BaseModel):
    policy: BaselinePolicy
    essential_service_survival_rate: float
    cascade_collapses_averted: int
    total_life_hours_protected: float
    unmet_critical_population_hours: float
    worst_sector_deprivation_pct: float
    gini_coefficient: float
    computation_time_ms: float
    receipt: Optional[DecisionReceipt] = None
    timeline: List[SimulationStep]


class BenchmarkComparison(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_description: str
    time_horizon_m: int
    policies_evaluated: Dict[str, PolicyEvaluationResult]
    winner_policy: str
    lifeline_delta_life_hours: float
    lifeline_pct_improvement_vs_greedy: float
    lifeline_pct_improvement_vs_fcfs: float
