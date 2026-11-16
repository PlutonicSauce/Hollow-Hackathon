import { useEffect, useState } from "react";
import type { CoordinationCertificate, Evaluation } from "./types";
import { CommunityExperiment } from "./CommunityExperiment";
import { CoordinationNetwork } from "./CoordinationNetwork";
import "./coordination.css";

const number = (value: number) => value.toLocaleString("en-US");

export function CoordinationExplorer({ evaluation, certificate, stale }: {
  evaluation: Pick<Evaluation, "scenario" | "optimization" | "coordination_verification"> & Partial<Pick<Evaluation, "traces">>;
  certificate: CoordinationCertificate;
  stale: boolean;
}) {
  const scenario = evaluation.scenario;
  const ids = certificate.actions.map((action) => action.intervention_id);
  const [selected, setSelected] = useState(ids);
  const [minute, setMinute] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [comparison, setComparison] = useState("subsets");
  const choose = (subset: string[]) => { setSelected(subset); setComparison("subsets"); setPlaying(false); };
  useEffect(() => { if (stale) setPlaying(false); }, [stale]);
  useEffect(() => {
    if (!playing || stale) return;
    const timer = window.setInterval(() => setMinute((current) => {
      if (current >= scenario.horizon_minutes) { setPlaying(false); return current; }
      return current + 1;
    }), 850);
    return () => window.clearInterval(timer);
  }, [playing, stale, scenario.horizon_minutes]);
  const row = certificate.subset_scores.find((candidate) =>
    candidate.intervention_ids.length === selected.length &&
    candidate.intervention_ids.every((id) => selected.includes(id)),
  );
  const resourceName = (id: string) => {
    const action = certificate.actions.find((item) => item.intervention_id === id);
    return scenario.resources.find((resource) => resource.id === action?.resource_id)?.name ?? id;
  };
  const assetName = (id: string) => scenario.assets.find((asset) => asset.id === id)?.name ?? id;
  const subsetName = (subset: string[]) => subset.length === 0 ? "No actions"
    : subset.length === ids.length ? ids.length === 2 ? "Both actions" : "Full response"
    : subset.map(resourceName).join(" + ") + (subset.length === 1 ? " only" : "");
  const isolated = certificate.actions.length === 2 && certificate.kind === "complementary" &&
    certificate.subset_scores.filter((item) => item.intervention_ids.length === 1)
      .every((item) => item.weighted_service_person_minutes <= certificate.empty_score);
  const report = evaluation.coordination_verification;
  const checked = report?.status === "passed" && report.checks.length > 0 && report.checks.every((check) => check.passed);
  const greedyPlan = evaluation.optimization.baseline_comparisons.find((item) => item.baseline === "greedy")?.plan;
  const baseline = evaluation.optimization.baseline_comparisons.find((item) => item.baseline === comparison);
  const baselineTrace = evaluation.traces?.[comparison as keyof NonNullable<Evaluation["traces"]>];
  const shownRow = comparison === "subsets" ? row : baseline && baselineTrace?.length === scenario.horizon_minutes + 1 && baselineTrace.every((step) => scenario.assets.every((asset) => step.assets.some((state) => state.asset_id === asset.id))) ? {
    weighted_service_person_minutes: baseline.plan.objective.weighted_service_person_minutes,
    served: baseline.plan.demand_metrics.map((metric) => ({demand_id: metric.demand_id, served_minutes: metric.served_minutes})),
    availability: scenario.assets.map((asset) => ({asset_id: asset.id, service_available: baselineTrace.map((step) => step.assets.find((state) => state.asset_id === asset.id)!.service_available)})),
  } : undefined;
  const shownName = comparison === "subsets" ? subsetName(selected) : comparison === "greedy" ? "Greedy response" : "Static priority";
  const recommendedSelected = comparison === "subsets" && selected.length === ids.length;
  const selectedActions = comparison === "subsets" ? selected : baseline?.plan.interventions.map((action) => action.id) ?? [];
  const setsText = (sets: string[][]) => sets.map((set) => set.length ? set.map(resourceName).join(" + ") : "No actions").join("; ");

  return (
    <section id="coordination" className="coordination-section" aria-labelledby="coordination-title">
      <header className="coordination-heading">
        <h1 id="coordination-title">{isolated ? "Water and ventilation are down.\nTwo crews can bring them back." : ids.length ? "What does each action contribute?" : "Service without assigned backup"}</h1>
        <p>{isolated
          ? "For this underground community, a shared pump needs power and water. Neither crew can restore its services alone. Try switching either crew off."
          : "Choose a response and see which community services remain available. These are recorded outcomes from the Python model."}</p>
      </header>
      {!checked && <p role="alert" className="coord-stale">Certificate replay checks failed or were not supplied. Exploration is disabled; recompute before relying on these claims.</p>}
      {stale && <p className="coord-stale" role="status">Inputs have changed. This evidence belongs to the previous run. Confirm and recompute to explore the new response.</p>}
      <div className={`coord-explorer ${stale ? "results-stale" : ""}`}>
        <div className="coord-choices">
          <fieldset disabled={stale || !checked}>
            <legend>{isolated ? "Choose crews for the shared pump" : "Explore recommended assignments"}</legend>
            {certificate.actions.map((action) => {
              const included = selected.includes(action.intervention_id);
              const asset = scenario.assets.find((item) => item.id === action.target_asset_id);
              const service = asset?.dependency_groups.find((group) => group.id === action.dependency_group_id)?.service_type;
              return (
                <label className={`coord-switch ${included ? "is-included" : ""}`} key={action.intervention_id}>
                  <input type="checkbox" role="switch" checked={included}
                    aria-label={`${resourceName(action.intervention_id)} intervention`}
                    onChange={() => choose(included ? selected.filter((id) => id !== action.intervention_id) : [...selected, action.intervention_id])} />
                  <span><strong>{resourceName(action.intervention_id)}</strong>
                    <span>{service} backup at {assetName(action.target_asset_id)}</span>
                    <small>{included ? "Included" : "Excluded"}</small></span>
                </label>
              );
            })}
            {!ids.length && <p>No response resource is assigned in this plan. The timeline still includes natural fault endings and reserves.</p>}
          </fieldset>
          <details className="coord-outcomes">
            <summary>{certificate.subset_scores.length} replayed outcomes</summary>
            <div aria-label="Replayed action subsets">
              {certificate.subset_scores.map((subset) => {
                const active = comparison === "subsets" && subset.intervention_ids.length === selected.length && subset.intervention_ids.every((id) => selected.includes(id));
                return <button key={JSON.stringify(subset.intervention_ids)} type="button" disabled={stale || !checked}
                  aria-pressed={active} onClick={() => choose(subset.intervention_ids)}>
                  <span>{subsetName(subset.intervention_ids)}</span><strong>{number(subset.weighted_service_person_minutes)}</strong>
                </button>;
              })}
            </div>
          </details>
          <a className="coord-audit-link" href="#decision-audit">Can I check this result? →</a>
        </div>
        <div className="coord-outcome">
          <div className="coord-view-heading"><span>{recommendedSelected ? "Recommended response" : "Exploring a counterfactual"}</span><strong>{shownName}</strong></div>
          {comparison !== "subsets" && <p className="experiment-scope">Different assignment: {baseline?.plan.interventions.map((action) => `${scenario.resources.find((resource) => resource.id === action.resource_id)?.name} → ${assetName(action.target_asset_id)}`).join("; ") || "No crew assigned"}.</p>}
          <CommunityExperiment scenario={scenario} availability={shownRow?.availability} minute={minute}
            actions={comparison === "subsets" ? evaluation.optimization.selected_plan.interventions.filter((action) => selectedActions.includes(action.id)) : baseline?.plan.interventions ?? []} />
          <div className="coord-replay">
            <button type="button" disabled={stale || !checked || !shownRow} onClick={() => {if (!playing) setMinute(0); setPlaying(!playing);}}>{playing ? "Pause recovery" : "Watch recovery"}</button>
            <label>Minute {minute} of {scenario.horizon_minutes}<input type="range" min="0" max={scenario.horizon_minutes} value={minute} disabled={stale || !checked} aria-label="Counterfactual minute" onChange={(event) => {setMinute(Number(event.target.value)); setPlaying(false);}} /></label>
            <button type="button" disabled={stale || !checked} onClick={() => {setMinute(0);setPlaying(false);}}>Reset</button>
          </div>
          <p className="coord-observed">{scenario.demands.filter((demand) => shownRow?.availability.find((item) => item.asset_id === demand.served_by_asset_id)?.service_available[minute] === true).length} of {scenario.demands.length} community services available at minute {minute}</p>
          <p className="coord-phase">{minute === 0 ? "Initial state · Includes any backup arriving at minute 0" : minute === scenario.horizon_minutes ? "End boundary · Not an additional service minute" : selectedActions.length ? "Response underway · Recorded simulator state" : "Without response · Recorded simulator state"}</p>
          <details className="recovery-detail"><summary>Explore the network and full recovery</summary>
          <CoordinationNetwork scenario={scenario} availability={shownRow?.availability} minute={minute} selectedActions={selectedActions}
            actions={comparison === "subsets" ? evaluation.optimization.selected_plan.interventions : baseline?.plan.interventions ?? []} />
          <div className="coord-results">

          <div role="status" aria-live="polite" aria-atomic="true" className="coord-score">
            <strong>{shownRow ? number(shownRow.weighted_service_person_minutes) : "Unavailable"}</strong>
            <span>priority-weighted service-person-minutes</span><small>Across the full {scenario.horizon_minutes}-minute window</small>
            <b>{shownName}{shownRow && shownRow.weighted_service_person_minutes === certificate.empty_score ? " · same score as no actions" : ""}</b>
          </div>
          {shownRow ? <>
            <div className="coord-demands">
              {scenario.demands.map((demand) => <ServiceTimeline key={demand.id}
                title={`${demand.community_id.replaceAll("-", " ")}: ${demand.service_type}`}
                population={demand.population} horizon={scenario.horizon_minutes} minute={minute}
                series={shownRow.availability.find((item) => item.asset_id === demand.served_by_asset_id)?.service_available}
                servedMinutes={shownRow.served.find((item) => item.demand_id === demand.id)?.served_minutes} />)}
            </div>

          </> : <p role="alert">The server did not provide a replay for this subset. Recompute before using this evidence.</p>}
          </div>
          <div className="coord-time-key"><span>Minute 0</span><span>Minute {scenario.horizon_minutes}</span></div>
          <p className="coord-explainer">Solid segments: available. Hatched segments: unavailable. Each segment is one modeled minute. The final boundary adds no service time.</p>
          <p className="coord-explainer">Temporary backup supplies missing inputs; it does not repair physical faults. These toggles explore this response’s actions, not every possible assignment.</p>
          </details>
        </div>
      </div>
          <details className="coord-comparisons"><summary>Compare other responses</summary><h3>Why the simpler response misses it</h3>
            <p>Same crews. Different assignments. The recommended response scores {number(certificate.plan_score)} priority-weighted service-person-minutes.{certificate.plan_score > certificate.greedy.final_score && certificate.greedy.final_score > 0 ? ` That is ${Math.round((certificate.plan_score / certificate.greedy.final_score - 1) * 100)}% higher than greedy.` : ""}</p>
            {evaluation.optimization.baseline_comparisons.filter((item) => item.baseline !== "no_intervention").map((item) =>
              <button type="button" key={item.baseline} disabled={stale || !checked || !evaluation.traces}
                aria-pressed={comparison === item.baseline} onClick={() => {setComparison(item.baseline); setPlaying(false);}}>
                <span>{item.baseline === "greedy" ? "Greedy response" : "Static priority"}</span><strong>{number(item.plan.objective.weighted_service_person_minutes)}</strong>
              </button>)}
            <p className="coord-comparison-note">{comparison === "greedy" ? "Greedy adds the best immediate gain, one crew at a time." : comparison === "static_priority" ? "Static priority favors direct demand at each destination." : evaluation.optimization.exhaustive_search_complete ? "The recommended plan checks every feasible assignment in this supported search." : "Search incomplete. No optimality claim is established."}</p>
          </details>
      <details className="coord-technical"><summary>Understand the coordination evidence</summary>
      <p className="coord-definition">The service score adds population × available minutes × priority weight across demand records. The same community may need multiple services. This is a synthetic model score, not a count of people saved or evidence of real-world emergency safety.</p>
      <div className="coord-claims">
        <div><h3>{ids.length > 2 ? "Higher-order interaction" : "Joint benefit"}</h3>
          <p>{ids.length >= 2
            ? `${number(certificate.joint_gain)} weighted service-person-minutes is the ${ids.length === 2 ? "two-action interaction: both minus each single action, plus no actions" : `${ids.length}-action Harsanyi dividend, calculated across all subsets. It does not describe all lower-order interactions`}.`
            : "A coordination effect needs at least two actions. No multi-action synergy is claimed here."}</p>
        </div>
        <div><h3>Is each action necessary?</h3>
          {certificate.necessity.length ? certificate.necessity.map((claim) => <p key={claim.intervention_id}>
            Without {resourceName(claim.intervention_id)}: {number(claim.score_without)}{claim.necessary ? `, a loss of ${number(claim.loss_without)}.` : ". Removing it does not lower this score."}
          </p>) : <p>No assigned action to remove.</p>}
        </div>
        <div><h3>Minimal sufficient subsets of this response</h3>
          <p>{setsText(certificate.full_recovery_minimal_sets)} matches every demand’s served-minute total under the full response. No listed set contains a smaller sufficient subset. This is inclusion-minimality within the recommended actions, not a globally smallest plan or full recovery.</p>
        </div>
        <div><h3>{certificate.greedy.trap_detected ? "Why greedy misses this response" : "Comparison with greedy"}</h3>
          <p>Greedy scores {number(certificate.greedy.final_score)}; this response scores {number(certificate.plan_score)}.
            {certificate.greedy.trap_detected ? ` It stops ${number(certificate.greedy.shortfall_versus_plan)} below this response because no further single addition gives a positive immediate gain.` : " No advantage over greedy is claimed by this certificate."}</p>
          {certificate.greedy.steps.map((step) => {
            const action = greedyPlan?.interventions.find((item) => item.id === step.intervention_id);
            const resource = scenario.resources.find((item) => item.id === action?.resource_id);
            return <p key={step.intervention_id}>{resource?.name ?? "Greedy action"}{action ? ` → ${assetName(action.target_asset_id)}` : ""}: +{number(step.marginal_gain)}.</p>;
          })}
        </div>
      </div>
      <details className="coord-evidence">
        <summary>What this evidence does and does not show</summary>
        <p>{checked ? `${report.checks.length} certificate replay checks passed during evaluation.` : "Certificate replay checks did not pass or were not supplied. Do not treat this evidence as checked."}</p>
        <p>The builder and verifier share the simulator and claim formulas. This is replay consistency checking, not fully independent verification. The separate Decision Receipt audit remains available below.</p>
        <ul>{certificate.limitations.statements.map((statement) => <li key={statement}>{statement}</li>)}</ul>
        {report && <ul aria-label="Certificate replay checks">{report.checks.map((check) => <li key={check.name}>{check.name.replaceAll("_", " ")}: <strong>{check.passed ? "passed" : "failed"}</strong></li>)}</ul>}
        <h4>Per-demand sufficient subsets</h4>
        {certificate.demand_sufficiency.map((demand) => <p key={demand.demand_id}>{scenario.demands.find((item) => item.id === demand.demand_id)?.community_id.replaceAll("-", " ") ?? demand.demand_id}: {demand.required_served_minutes} served minutes · {setsText(demand.minimal_sets)}</p>)}
        <p>Scenario SHA-256 <code>{certificate.scenario_sha256}</code></p>
        <p>Certificate SHA-256 <code>{certificate.certificate_sha256}</code></p>
        <details><summary>Inspect certificate JSON</summary><pre>{JSON.stringify(certificate, null, 2)}</pre></details>
      </details>
      </details>
    </section>
  );
}

function ServiceTimeline({ title, population, horizon, series, servedMinutes, minute }: {
  title: string; population?: number; horizon: number; series?: boolean[]; servedMinutes?: number; minute?: number;
}) {
  if (!series || series.length !== horizon + 1) return <p>{title}: replay series unavailable.</p>;
  const served = servedMinutes ?? series.slice(0, horizon).filter(Boolean).length;
  return <div className="coord-service">
    <div className="coord-service-label"><strong>{title}</strong><span>{population !== undefined ? `${number(population)} modeled people · ` : ""}{served} of {horizon} minutes available</span></div>
    <div className="coord-intervals" role="img" aria-label={`${title}: ${served} of ${horizon} minutes available`} style={{gridTemplateColumns: `repeat(${horizon}, minmax(0, 1fr))`}}>
      {series.slice(0, horizon).map((available, minuteIndex) => <span key={minuteIndex} className={`${available ? "interval-available" : "interval-unavailable"} ${minute === minuteIndex ? "at-minute" : ""}`} title={`Minute ${minuteIndex}–${minuteIndex + 1}: ${available ? "available" : "unavailable"}`} />)}
    </div>
    <details className="coord-minute-details"><summary>Minute details for {title}</summary>
      <ol>{series.map((available, minute) => <li key={minute}>Minute {minute}{minute === horizon ? " (end boundary, not counted)" : `–${minute + 1}`}: {available ? "available" : "unavailable"}</li>)}</ol>
    </details>
  </div>;
}
