import type { Plan, Scenario } from "./types";

/** A reading of recorded availability, never a browser simulation. */
export function CommunityExperiment({scenario, availability, actions, minute}: {
  scenario: Scenario; availability?: {asset_id:string; service_available:boolean[]}[];
  actions: Plan["interventions"]; minute:number;
}) {
  const available = (id:string) => availability?.find((item) => item.asset_id === id)?.service_available[minute];
  const pump = scenario.assets.find((asset) => asset.id === "pump");
  const coupled = scenario.id === "coupled-water-power-restoration" && pump;
  return <div className="community-experiment">
    {coupled && <div className="pump-experiment">
      <div className="pump-inputs" aria-label="Required pump inputs">{pump.dependency_groups.map((group) => {
        const action = actions.find((item) => item.target_asset_id === pump.id && item.dependency_group_id === group.id);
        const resource = scenario.resources.find((item) => item.id === action?.resource_id);
        const route = resource?.travel_times.find((item) => item.asset_id === pump.id);
        const arrival = action ? action.dispatch_minute + (route?.travel_minutes ?? 0) + (route?.setup_minutes ?? 0) : null;
        const active = action && arrival !== null && minute >= arrival && minute < scenario.horizon_minutes && (action.duration_minutes === null || minute < arrival + action.duration_minutes);
        const providerAvailable = group.provider_asset_ids.some((id) => available(id) === true);
        return <div className={active || providerAvailable ? "input-present" : "input-missing"} key={group.id}>
          <strong>{group.service_type === "power" ? "Power" : "Water"}</strong>
          <span>{active ? "Temporary backup connected" : providerAvailable ? "Upstream supply available" : arrival !== null && minute < arrival ? `Crew arrives at minute ${arrival}` : "Required input missing"}</span>
        </div>;
      })}</div>
      <div className={`shared-pump ${available(pump.id) ? "pump-running" : ""}`}>
        <span aria-hidden="true">{available(pump.id) ? "✓" : "—"}</span><h2>Shared pump</h2>
        <strong>{available(pump.id) === undefined ? "Replay unavailable" : available(pump.id) ? "Supplying services" : "Unable to supply services"}</strong>
        <p>Needs power <b>and</b> water.</p>
      </div>
    </div>}
    <div className="community-services" aria-label="Recorded community outcomes">{scenario.demands.map((demand) => {
      const state = available(demand.served_by_asset_id);
      return <div className={state ? "community-served" : "community-unserved"} key={demand.id}>
        <span className="community-service-symbol" aria-hidden="true">{state ? "✓" : "—"}</span>
        <div><h3>{demand.service_type === "air" ? "Ventilation" : demand.service_type.replace(/^./, (char) => char.toUpperCase())}</h3>
          <strong>{state === undefined ? "Replay unavailable" : state ? "Available" : "Unavailable"}</strong>
          <p>{demand.community_id.replaceAll("-", " ")} · {demand.population} modeled people</p></div>
      </div>;
    })}</div>
    <p className="experiment-scope">Recorded state at minute {minute}. Temporary backup supports missing inputs; it does not repair physical faults.</p>
  </div>;
}
