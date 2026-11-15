import { useState } from "react";
import type { CoordinationCertificate, Evaluation } from "./types";
import "./coordination.css";

const number = (value: number) => value.toLocaleString("en-US");

export function CoordinationExplorer({ evaluation, certificate, stale }: {
  evaluation: Pick<Evaluation, "scenario" | "optimization" | "coordination_verification">;
  certificate: CoordinationCertificate;
  stale: boolean;
}) {
  const scenario = evaluation.scenario;
  const ids = certificate.actions.map((action) => action.intervention_id);
  const [selected, setSelected] = useState(ids);
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
  const targetIds = [...new Set(certificate.actions.map((action) => action.target_asset_id))]
    .filter((id) => !scenario.demands.some((demand) => demand.served_by_asset_id === id));
  const greedyPlan = evaluation.optimization.baseline_comparisons.find((item) => item.baseline === "greedy")?.plan;
  const setsText = (sets: string[][]) => sets.map((set) => set.length ? set.map(resourceName).join(" + ") : "No actions").join("; ");

  return (
    <section id="coordination" className="coordination-section" aria-labelledby="coordination-title">
      <header className="coordination-heading">
        <h2 id="coordination-title">{isolated ? "These actions only work together" : ids.length ? "What does each action contribute?" : "Service without assigned backup"}</h2>
        <p>{isolated
          ? `Neither recommended action alone improves on no actions. Together they score ${number(certificate.plan_score)}. Switch actions off to explore why.`
          : "Explore subsets of the recommended response. Every outcome below comes from a Python simulator replay, using the same scenario inputs."}</p>
      </header>
      {!checked && <p role="alert" className="coord-stale">Certificate replay checks failed or were not supplied. Exploration is disabled; recompute before relying on these claims.</p>}
      {stale && <p className="coord-stale" role="status">Inputs have changed. This evidence belongs to the previous run. Confirm and recompute to explore the new response.</p>}
      <div className={`coord-explorer ${stale ? "results-stale" : ""}`}>
        <div className="coord-choices">
          <fieldset disabled={stale || !checked}>
            <legend>What if only some actions happen?</legend>
            {certificate.actions.map((action) => {
              const included = selected.includes(action.intervention_id);
              const asset = scenario.assets.find((item) => item.id === action.target_asset_id);
              const service = asset?.dependency_groups.find((group) => group.id === action.dependency_group_id)?.service_type;
              return (
                <label className={`coord-switch ${included ? "is-included" : ""}`} key={action.intervention_id}>
                  <input type="checkbox" role="switch" checked={included}
                    aria-label={`${resourceName(action.intervention_id)} intervention`}
                    onChange={() => setSelected((current) => included
                      ? current.filter((id) => id !== action.intervention_id)
                      : [...current, action.intervention_id])} />
                  <span><strong>{resourceName(action.intervention_id)}</strong>
                    <span>{service} backup at {assetName(action.target_asset_id)}</span>
                    <small>{included ? "Included" : "Excluded"}</small></span>
                </label>
              );
            })}
            {!ids.length && <p>No response resource is assigned in this plan. The timeline still includes natural fault endings and reserves.</p>}
          </fieldset>
          <details className="coord-outcomes" open={ids.length <= 2}>
            <summary>{certificate.subset_scores.length} replayed outcomes</summary>
            <div aria-label="Replayed action subsets">
              {certificate.subset_scores.map((subset) => {
                const active = subset.intervention_ids.length === selected.length && subset.intervention_ids.every((id) => selected.includes(id));
                return <button key={JSON.stringify(subset.intervention_ids)} type="button" disabled={stale || !checked}
                  aria-pressed={active} onClick={() => setSelected(subset.intervention_ids)}>
                  <span>{subsetName(subset.intervention_ids)}</span><strong>{number(subset.weighted_service_person_minutes)}</strong>
                </button>;
              })}
            </div>
          </details>
        </div>
        <div className="coord-outcome">
          <div role="status" aria-live="polite" aria-atomic="true" className="coord-score">
            <strong>{row ? number(row.weighted_service_person_minutes) : "Unavailable"}</strong>
            <span>weighted service-person-minutes</span>
            <b>{subsetName(selected)}{row && row.weighted_service_person_minutes === certificate.empty_score ? " · same score as no actions" : ""}</b>
          </div>
          {row ? <>
            <div className="coord-demands">
              {scenario.demands.map((demand) => <ServiceTimeline key={demand.id}
                title={`${demand.community_id.replaceAll("-", " ")}: ${demand.service_type}`}
                population={demand.population} horizon={scenario.horizon_minutes}
                series={row.availability.find((item) => item.asset_id === demand.served_by_asset_id)?.service_available}
                servedMinutes={row.served.find((item) => item.demand_id === demand.id)?.served_minutes} />)}
            </div>
            {targetIds.length > 0 && <div className="coord-shared"><h3>Shared infrastructure along the way</h3>
              {targetIds.map((id) => <ServiceTimeline key={id} title={assetName(id)} horizon={scenario.horizon_minutes}
                series={row.availability.find((item) => item.asset_id === id)?.service_available} />)}
            </div>}
          </> : <p role="alert">The server did not provide a replay for this subset. Recompute before using this evidence.</p>}
          <div className="coord-time-key"><span>Minute 0</span><span>Minute {scenario.horizon_minutes}</span></div>
          <p className="coord-explainer">Solid segments: available. Hatched segments: unavailable. Each segment is one modeled minute. The final boundary adds no service time.</p>
          <p className="coord-explainer">Temporary backup supplies missing inputs; it does not repair physical faults. These toggles explore this response’s actions, not every possible assignment.</p>
        </div>
      </div>
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
    </section>
  );
}

function ServiceTimeline({ title, population, horizon, series, servedMinutes }: {
  title: string; population?: number; horizon: number; series?: boolean[]; servedMinutes?: number;
}) {
  if (!series || series.length !== horizon + 1) return <p>{title}: replay series unavailable.</p>;
  const served = servedMinutes ?? series.slice(0, horizon).filter(Boolean).length;
  return <div className="coord-service">
    <div className="coord-service-label"><strong>{title}</strong><span>{population !== undefined ? `${number(population)} modeled people · ` : ""}{served} of {horizon} minutes available</span></div>
    <div className="coord-intervals" role="img" aria-label={`${title}: ${served} of ${horizon} minutes available`} style={{gridTemplateColumns: `repeat(${horizon}, minmax(0, 1fr))`}}>
      {series.slice(0, horizon).map((available, minute) => <span key={minute} className={available ? "interval-available" : "interval-unavailable"} title={`Minute ${minute}–${minute + 1}: ${available ? "available" : "unavailable"}`} />)}
    </div>
    <details className="coord-minute-details"><summary>Minute details for {title}</summary>
      <ol>{series.map((available, minute) => <li key={minute}>Minute {minute}{minute === horizon ? " (end boundary, not counted)" : `–${minute + 1}`}: {available ? "available" : "unavailable"}</li>)}</ol>
    </details>
  </div>;
}
