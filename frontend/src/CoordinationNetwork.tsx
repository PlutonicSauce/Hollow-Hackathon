import { useState } from "react";
import { WorkspaceIcon } from "./WorkspaceIcon";
import type { Plan, Scenario } from "./types";

/** Layout only: all service states are read from a recorded Python replay. */
export function CoordinationNetwork({ scenario, availability, minute, selectedActions, actions }: {
  scenario: Scenario;
  availability?: {asset_id: string; service_available: boolean[]}[];
  minute: number;
  selectedActions: string[];
  actions: Plan["interventions"];
}) {
  const [inspected, setInspected] = useState("");
  const available = (id: string) => availability?.find((item) => item.asset_id === id)?.service_available[minute];
  const depth = new Map<string, number>();
  const level = (id: string): number => {
    if (depth.has(id)) return depth.get(id)!;
    const asset = scenario.assets.find((item) => item.id === id);
    const providers = asset?.dependency_groups.flatMap((group) => group.provider_asset_ids) ?? [];
    const result = providers.length ? 1 + Math.max(...providers.map(level)) : 0;
    depth.set(id, result);
    return result;
  };
  scenario.assets.forEach((asset) => level(asset.id));
  const maxLevel = Math.max(0, ...depth.values());
  const columns = Array.from({length:maxLevel + 1}, (_, index) => scenario.assets.filter((asset) => depth.get(asset.id) === index));
  const positions = new Map(scenario.assets.map((asset) => {
    const column = depth.get(asset.id)!;
    const items = columns[column];
    return [asset.id, {x: (column + .5) * 100 / (maxLevel + 1), y: (items.indexOf(asset) + 1) * 100 / (items.length + 1)}];
  }));
  const asset = scenario.assets.find((item) => item.id === inspected);
  const related = new Set([inspected, ...asset?.dependency_groups.flatMap((group) => group.provider_asset_ids) ?? [], ...scenario.assets.filter((item) => item.dependency_groups.some((group) => group.provider_asset_ids.includes(inspected))).map((item) => item.id)]);
  return <div className="discovery-network">
    <div className="discovery-flow" aria-label={`Recorded infrastructure state at minute ${minute}`}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {scenario.assets.flatMap((target) => target.dependency_groups.flatMap((group) => group.provider_asset_ids.map((provider) => {
          const from = positions.get(provider)!; const to = positions.get(target.id)!;
          return <path key={`${group.id}:${provider}`} d={`M${from.x},${from.y} C${(from.x+to.x)/2},${from.y} ${(from.x+to.x)/2},${to.y} ${to.x},${to.y}`}
            className={`${available(provider) === true ? "supply-on" : "supply-off"} ${inspected && !related.has(provider) && !related.has(target.id) ? "flow-dimmed" : ""}`} />;
        })))}
      </svg>
      {columns.map((column,index) => <div className="discovery-column" key={index}>
        {column.map((item) => {
          const state = available(item.id);
          const fault = scenario.faults.some((fault) => fault.asset_id === item.id && fault.start_minute <= minute && (fault.end_minute === null || minute < fault.end_minute));
          const status = state === undefined ? "Replay unavailable" : fault ? "Physical failure" : state ? "Service available" : "Service unavailable";
          const backed = actions.filter((action) => selectedActions.includes(action.id) && action.target_asset_id === item.id);
          return <button type="button" key={item.id} aria-pressed={inspected === item.id} onClick={() => setInspected(inspected === item.id ? "" : item.id)}
            className={`discovery-asset ${state ? "asset-on" : "asset-off"} ${fault ? "asset-failed" : ""} ${inspected && !related.has(item.id) ? "flow-dimmed" : ""}`}>
            <span className="asset-state-symbol" aria-hidden="true"><WorkspaceIcon name={fault ? "failed" : state ? "available" : "unavailable"} /></span>
            <strong>{item.name.replace(/^(Failed |Interrupted |Finite )/, "").replace("deep-sector ", "").replace(/^./, (char) => char.toUpperCase())}</strong><small>{status}</small>
            {backed.length > 0 && <span className="asset-backup">{backed.length} backup {backed.length === 1 ? "input" : "inputs"} assigned</span>}
          </button>;
        })}
      </div>)}
    </div>
    <div className="discovery-caption">Solid: available supply. Dashed: unavailable. Select an asset to inspect its inputs.</div>
    <details className="discovery-dependencies" open={Boolean(asset)} hidden={!asset}>
      <summary>Inspect dependency rules{asset ? ` · ${asset.name}` : " · Select an asset"}</summary>
      {asset ? <><p>{asset.dependency_groups.length ? "Every required group below must be satisfied (AND). Alternatives within one group use OR." : "This asset has no upstream dependency groups."}</p>
        <ul>{asset.dependency_groups.map((group) => <li key={group.id}><strong>{group.service_type}</strong>: {group.provider_asset_ids.map((id) => `${scenario.assets.find((item) => item.id === id)?.name} (${available(id) === undefined ? "unknown" : available(id) ? "available" : "unavailable"})`).join(" OR ")}</li>)}</ul>
        <p>Assigned temporary backup supports its target input group. Reserve can sustain service despite missing input; availability above is read from the simulator, not inferred from these connections.</p></> : <p>Choose an infrastructure asset to see its required inputs and connected services.</p>}
    </details>
  </div>;
}
