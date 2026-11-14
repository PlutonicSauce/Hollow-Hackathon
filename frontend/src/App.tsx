import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  Asset,
  Evaluation,
  Plan,
  Receipt,
  Scenario,
  ScenarioChoice,
  TimeStep,
  VerificationReport,
} from "./types";

type PlanKey = "no_intervention" | "static_priority" | "greedy" | "optimized";

const PLAN_LABELS: Record<PlanKey, string> = {
  no_intervention: "No response",
  static_priority: "Static priority",
  greedy: "Greedy response",
  optimized: "LIFELINE optimized",
};

const CHECKS = [
  ["schema_status", "Receipt schema"],
  ["version_status", "Model versions"],
  ["integrity_status", "Payload integrity"],
  ["input_status", "Scenario inputs"],
  ["replay_status", "Deterministic replay"],
  ["baseline_status", "Counterfactuals"],
  ["optimality_status", "Exhaustive optimality"],
] as const;

const numberFormat = new Intl.NumberFormat("en-US");
const formatNumber = (value: number) => numberFormat.format(value);

function App() {
  const [choices, setChoices] = useState<ScenarioChoice[]>([]);
  const [scenarioKey, setScenarioKey] = useState("coupled-utility");
  const [baseScenario, setBaseScenario] = useState<Scenario | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [availableResourceIds, setAvailableResourceIds] = useState<string[]>([]);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [planKey, setPlanKey] = useState<PlanKey>("optimized");
  const [minute, setMinute] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");
  const [verification, setVerification] = useState<VerificationReport | null>(null);
  const [tolerancePpm, setTolerancePpm] = useState(0);
  const [resultsStale, setResultsStale] = useState(false);
  const evaluationRequest = useRef(0);
  const inputRevision = useRef(0);
  const verificationRequest = useRef(0);

  const runEvaluation = useCallback(
    async (input: Scenario, tolerance: number) => {
      const requestId = ++evaluationRequest.current;
      const requestRevision = inputRevision.current;
      setLoading(true);
      setResultsStale(true);
      setPlaying(false);
      setError("");
      setVerification(null);
      verificationRequest.current += 1;
      setVerifying(false);
      try {
        const result = await api.evaluate(input, {
          primary_tolerance_ppm: tolerance,
        });
        if (
          requestId === evaluationRequest.current &&
          requestRevision === inputRevision.current
        ) {
          setEvaluation(result);
          setResultsStale(false);
          setMinute(0);
          setPlanKey("optimized");
        }
      } catch (reason) {
        if (
          requestId === evaluationRequest.current &&
          requestRevision === inputRevision.current
        ) {
          setError(reason instanceof Error ? reason.message : "The scenario could not be evaluated.");
        }
      } finally {
        if (requestId === evaluationRequest.current) setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    let active = true;
    api
      .scenarios()
      .then((items) => {
        if (active) setChoices(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load scenarios.");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const requestId = ++evaluationRequest.current;
    const requestRevision = ++inputRevision.current;
    setLoading(true);
    setPlaying(false);
    setEvaluation(null);
    setResultsStale(false);
    setScenario(null);
    setVerification(null);
    setVerifying(false);
    setError("");
    api
      .scenario(scenarioKey)
      .then(async (loaded) => {
        if (!active) return;
        setBaseScenario(loaded);
        setScenario(loaded);
        setAvailableResourceIds(loaded.resources.map((resource) => resource.id));
        const result = await api.evaluate(loaded, {
          primary_tolerance_ppm: tolerancePpm,
        });
        if (
          active &&
          requestId === evaluationRequest.current &&
          requestRevision === inputRevision.current
        ) {
          setEvaluation(result);
          setResultsStale(false);
          setMinute(0);
          setPlanKey("optimized");
        }
      })
      .catch((reason: unknown) => {
        if (
          active &&
          requestId === evaluationRequest.current &&
          requestRevision === inputRevision.current
        ) {
          setError(reason instanceof Error ? reason.message : "Could not load the incident.");
        }
      })
      .finally(() => {
        if (active && requestId === evaluationRequest.current) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [scenarioKey]);

  const trace = evaluation?.traces[planKey] ?? [];
  const currentStep = trace[Math.min(minute, Math.max(trace.length - 1, 0))];
  const choice = choices.find((item) => item.key === scenarioKey);
  const selectedPlan =
    planKey === "optimized"
      ? evaluation?.optimization.selected_plan
      : evaluation?.optimization.baseline_comparisons.find(
          (item) => item.baseline === planKey,
        )?.plan;
  const activeFaults = scenario?.faults.filter((fault) =>
    currentStep?.active_fault_ids.includes(fault.id),
  ) ?? [];
  const affectedServices = scenario?.demands
    .filter((demand) =>
      currentStep?.assets.find((state) => state.asset_id === demand.served_by_asset_id)
        ?.service_available === false,
    )
    .map((demand) => demand.service_type)
    .filter((service, index, all) => all.indexOf(service) === index) ?? [];

  useEffect(() => {
    if (!playing || !evaluation) return;
    const timer = window.setInterval(() => {
      setMinute((current) => {
        if (current >= evaluation.scenario.horizon_minutes) {
          setPlaying(false);
          return 0;
        }
        return current + 1;
      });
    }, 850);
    return () => window.clearInterval(timer);
  }, [playing, evaluation]);

  const changeScenario = (key: string) => {
    evaluationRequest.current += 1;
    inputRevision.current += 1;
    verificationRequest.current += 1;
    setScenarioKey(key);
    setTolerancePpm(0);
    setPlaying(false);
    setLoading(false);
    setResultsStale(false);
    setScenario(null);
    setBaseScenario(null);
    setAvailableResourceIds([]);
    setEvaluation(null);
    setVerification(null);
    setVerifying(false);
  };

  const markInputsDirty = () => {
    inputRevision.current += 1;
    verificationRequest.current += 1;
    setResultsStale(true);
    setVerification(null);
    setVerifying(false);
  };

  const setResourceAvailable = (resourceId: string, available: boolean) => {
    if (!baseScenario) return;
    markInputsDirty();
    const ids = new Set(availableResourceIds);
    if (available) ids.add(resourceId);
    else ids.delete(resourceId);
    const updatedIds = [...ids];
    setAvailableResourceIds(updatedIds);
    const resources = baseScenario.resources.filter((resource) => ids.has(resource.id));
    const updated = { ...baseScenario, resources, interventions: [] };
    setScenario(updated);
    setVerification(null);
  };

  const updateTravelTime = (resourceId: string, assetId: string, minutes: number) => {
    if (!scenario || !baseScenario) return;
    markInputsDirty();
    const update = (source: Scenario): Scenario => ({
      ...source,
      resources: source.resources.map((resource) =>
        resource.id !== resourceId
          ? resource
          : {
              ...resource,
              travel_times: resource.travel_times.map((route) =>
                route.asset_id === assetId
                  ? { ...route, travel_minutes: minutes }
                  : route,
              ),
            },
      ),
    });
    const updated = update(scenario);
    setScenario(updated);
    setBaseScenario(update(baseScenario));
    setVerification(null);
  };

  const recalculate = () => {
    if (scenario) void runEvaluation(scenario, tolerancePpm);
  };

  const verifyReceipt = async (receipt: Receipt) => {
    if (resultsStale || !evaluation || receipt !== evaluation.receipt) return;
    const requestId = ++verificationRequest.current;
    const requestRevision = inputRevision.current;
    setVerifying(true);
    setError("");
    try {
      const report = await api.verify(receipt);
      if (
        requestId === verificationRequest.current &&
        requestRevision === inputRevision.current
      ) {
        setVerification(report);
      }
    } catch (reason) {
      if (
        requestId === verificationRequest.current &&
        requestRevision === inputRevision.current
      ) {
        setError(reason instanceof Error ? reason.message : "Receipt verification failed.");
      }
    } finally {
      if (requestId === verificationRequest.current) setVerifying(false);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="LIFELINE home">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>LIFELINE</span>
        </a>
        <div className="topbar-center">
          <span className="workspace-dot" />
          HOLLOW · INCIDENT DESK
        </div>
        <div className="topbar-right">
          <span className="model-badge">DETERMINISTIC MODEL</span>
          <span className="live-indicator">
            <span /> LOCAL SIMULATION
          </span>
        </div>
      </header>

      <div className="content">
        <section className="page-heading">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> EMERGENCY RESPONSE / DECISION SUPPORT</div>
            <h1>See the cascade.<br /><span>Choose what holds.</span></h1>
            <p className="intro">
              Explore how a failure moves through the Hollow, then compare resource plans
              against the same deterministic simulation.
            </p>
          </div>
          <div className="incident-selector">
            <label htmlFor="scenario-select">ACTIVE SCENARIO</label>
            <select
              id="scenario-select"
              value={scenarioKey}
              onChange={(event) => changeScenario(event.target.value)}
              disabled={loading}
            >
              {choices.map((item) => (
                <option key={item.key} value={item.key}>{item.name}</option>
              ))}
            </select>
            <p>{choice?.description ?? "Loading scenario details…"}</p>
          </div>
        </section>

        {error && (
          <div className="error-banner" role="alert">
            <span className="error-symbol">!</span>
            <div><strong>Unable to complete that action</strong><span>{error}</span></div>
            <button type="button" onClick={() => setError("")} aria-label="Dismiss error">×</button>
          </div>
        )}
        {resultsStale && (
          <div className="stale-banner" role="status" aria-live="polite">
            <div>
              <strong>{loading ? "Recalculating edited inputs" : "Inputs have changed"}</strong>
              <span>Result panels and the trace still show the previous run. Recompute before treating them as current.</span>
            </div>
            <button type="button" onClick={recalculate} disabled={loading || !scenario}>
              {loading ? "Recomputing…" : "Apply changes"}
            </button>
          </div>
        )}

        <section className="incident-strip" aria-label="Incident summary">
          <div className="incident-title">
            <span className="incident-icon" aria-hidden="true"><Icon name="bolt" /></span>
            <div>
              <span className="eyebrow">WHAT HAPPENED</span>
              <strong>
                {activeFaults.map((fault) => {
                  const asset = scenario?.assets.find((item) => item.id === fault.asset_id);
                  return asset ? `${asset.provides} · ${asset.name}` : fault.id.replaceAll("-", " ");
                }).join("  ·  ") || "No active physical faults"}
              </strong>
              <small>
                {affectedServices.length
                  ? `Unavailable modeled services: ${affectedServices.join(", ")}`
                  : "No modeled demand currently unavailable"}
              </small>
            </div>
          </div>
          <div className="incident-fact"><span>HORIZON</span><strong>{scenario?.horizon_minutes ?? "—"} <small>min</small></strong></div>
          <div className="incident-fact"><span>ASSETS</span><strong>{scenario?.assets.length ?? "—"}</strong></div>
          <div className="incident-fact"><span>RESPONSE TEAMS</span><strong>{scenario?.resources.length ?? "—"}</strong></div>
          <div className="incident-status">
            <span className="status-pulse" />
            {loading ? "RECOMPUTING" : resultsStale ? "INPUTS CHANGED" : "MODEL READY"}
          </div>
        </section>

        <div className="section-label">
          <span>01</span> INFRASTRUCTURE STATE
          <span className="section-label-right">SERVICE AVAILABILITY AT MINUTE {minute}</span>
        </div>

        <section className="main-grid">
          <div className="panel network-panel">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">DEPENDENCY MAP</span>
                <h2>System topology</h2>
              </div>
              <div className="legend" aria-label="Asset status legend">
                <span><i className="legend-good" /> Working</span>
                <span><i className="legend-warn" /> Reserve</span>
                <span><i className="legend-backup" /> Temporary backup</span>
                <span><i className="legend-down" /> Unavailable</span>
                <span><i className="legend-fault" /> Physical fault</span>
              </div>
            </div>
            {resultsStale && evaluation && (
              <div className="stale-notice" role="status">
                Showing the previous run. Recompute to apply your edited inputs.
              </div>
            )}
            {scenario && currentStep ? (
              <DependencyMap
                assets={scenario.assets}
                step={currentStep}
                demands={scenario.demands}
                selectedPlan={selectedPlan}
                planLabel={PLAN_LABELS[planKey]}
                loading={loading || resultsStale}
              />
            ) : (
              <div className="map-placeholder">{loading ? "Evaluating scenario…" : "Select a scenario to view its dependency map."}</div>
            )}
            <div className="map-caption">
              <span><Icon name="branch" /> Arrows show provider → dependent</span>
              <span>Dashed amber = temporary support, not repair</span>
            </div>
          </div>

          <aside className={`panel response-panel ${resultsStale ? "results-stale" : ""}`}>
            <div className="panel-heading response-heading">
              <div>
                <span className="panel-kicker">COMPUTED RESPONSE</span>
                <h2>Recommended plan</h2>
              </div>
              {evaluation && (
                <span className={`exact-chip ${evaluation.optimization.exhaustive_search_complete ? "" : "bounded-search"}`}>
                  <Icon name={evaluation.optimization.exhaustive_search_complete ? "check" : "warning"} />
                  {evaluation.optimization.exhaustive_search_complete ? "EXACT" : "BOUNDED SEARCH"}
                </span>
              )}
            </div>
            {evaluation ? (
              <>
                <div className="recommendation-score">
                  <span>WEIGHTED SERVICE-PERSON-MINUTES</span>
                  <strong>{formatNumber(evaluation.optimization.selected_plan.objective.weighted_service_person_minutes)}</strong>
                  <small>Modeled service exposure · not people or outcomes</small>
                </div>
                {resultsStale && (
                  <div className="stale-notice" role="status">
                    Previous recommendation · these results do not include your edits.
                  </div>
                )}
                <div className="recommendation-lead">
                  {evaluation.optimization.selected_plan.interventions.length
                    ? `${evaluation.optimization.selected_plan.interventions.length} crew assignment${evaluation.optimization.selected_plan.interventions.length === 1 ? "" : "s"} selected from ${evaluation.optimization.candidate_plans} candidate plans.`
                    : "No assignment improves the configured objective; all teams remain available."}
                </div>
                <RecommendationInsight scenario={scenario ?? evaluation.scenario} evaluation={evaluation} />
                <div className="dispatch-list">
                  {evaluation.optimization.selected_plan.interventions.length ? (
                    evaluation.optimization.selected_plan.interventions.map((action) => {
                      const resource = scenario?.resources.find((item) => item.id === action.resource_id);
                      const asset = scenario?.assets.find((item) => item.id === action.target_asset_id);
                      const group = asset?.dependency_groups.find((item) => item.id === action.dependency_group_id);
                      const route = resource?.travel_times.find((item) => item.asset_id === action.target_asset_id);
                      return (
                        <div className="dispatch-row" key={action.id}>
                          <span className="dispatch-index">{String(evaluation.optimization.selected_plan.interventions.indexOf(action) + 1).padStart(2, "0")}</span>
                          <div>
                            <strong>{resource?.name ?? action.resource_id}</strong>
                            <span>→ {asset?.name ?? action.target_asset_id}</span>
                            <small>{group?.service_type ?? "service"} input · available minute {(route?.travel_minutes ?? 0) + (route?.setup_minutes ?? 0)}</small>
                          </div>
                          <Icon name="arrow" />
                        </div>
                      );
                    })
                  ) : (
                    <div className="idle-note">No beneficial dispatch in this scenario.</div>
                  )}
                </div>
                <div className="search-proof">
                  <span className={evaluation.optimization.exhaustive_search_complete ? "" : "search-limited"}>
                    <Icon name={evaluation.optimization.exhaustive_search_complete ? "check" : "warning"} />
                    {evaluation.optimization.exhaustive_search_complete ? "Exhaustive search complete" : "Search bound reached"}
                  </span>
                  <span>{formatNumber(evaluation.optimization.plans_evaluated)} plans evaluated</span>
                </div>
                <button className="primary-button" type="button" onClick={recalculate} disabled={loading || !scenario || !resultsStale}>
                  {loading ? <><span className="spinner" /> Recomputing…</> : <><Icon name="refresh" /> {resultsStale ? "Recalculate response" : "Results up to date"}</>}
                </button>
              </>
            ) : (
              <div className="map-placeholder">{loading ? "Computing response plans…" : "Run a scenario to see recommendations."}</div>
            )}
          </aside>
        </section>

        <section className="timeline-panel panel">
          <div className="timeline-title">
            <div><span className="panel-kicker">REPLAY</span><h2>Minute-by-minute state</h2></div>
            <div className="replay-controls">
              <label htmlFor="plan-select">SHOWING</label>
              <select id="plan-select" value={planKey} onChange={(event) => setPlanKey(event.target.value as PlanKey)} disabled={!evaluation}>
                {(Object.keys(PLAN_LABELS) as PlanKey[]).map((key) => (
                  <option key={key} value={key}>{PLAN_LABELS[key]}</option>
                ))}
              </select>
              <button
                className="play-button"
                type="button"
                onClick={() => {
                  if (minute >= (scenario?.horizon_minutes ?? 0)) setMinute(0);
                  setPlaying((value) => !value);
                }}
                disabled={!evaluation}
                aria-label={playing ? "Pause replay" : "Play replay"}
              >
                <Icon name={playing ? "pause" : "play"} />
              </button>
            </div>
          </div>
          <div className="scrubber">
            <span className="scrubber-start">T+00</span>
            <input
              aria-label="Simulation minute"
              type="range"
              min={0}
              max={scenario?.horizon_minutes ?? 1}
              value={Math.min(minute, scenario?.horizon_minutes ?? 0)}
              onChange={(event) => {
                setPlaying(false);
                setMinute(Number(event.target.value));
              }}
              disabled={!evaluation}
            />
            <span className="scrubber-end">T+{String(scenario?.horizon_minutes ?? 0).padStart(2, "0")}</span>
            <span className="minute-readout">MINUTE <strong>{String(minute).padStart(2, "0")}</strong></span>
          </div>
          <div className="timeline-events">
            {scenario?.faults.map((fault) => (
              <span className="event-chip event-fault" key={fault.id}>
              <i /> T+{fault.start_minute} · {fault.id.replaceAll("-", " ")}
              </span>
            ))}
            {selectedPlan?.interventions.map((action) => {
              const route = scenario?.resources.find((resource) => resource.id === action.resource_id)?.travel_times.find((item) => item.asset_id === action.target_asset_id);
              const arrival = action.dispatch_minute + (route?.travel_minutes ?? 0) + (route?.setup_minutes ?? 0);
              return (
                <span className="event-chip event-response" key={action.id}>
                  <i /> {action.resource_id} arrives · T+{arrival}
                </span>
              );
            })}
          </div>
        </section>

        <div className={`lower-grid ${resultsStale ? "results-stale" : ""}`}>
          <section className="panel comparison-panel">
            <div className="panel-heading">
              <div><span className="panel-kicker">COUNTERFACTUALS</span><h2>Same incident. Different plans.</h2></div>
              <span className="unit-note">weighted service-person-minutes</span>
            </div>
            {evaluation ? (
              <div className="comparison-list">
                {[
                  {
                    key: "no_intervention",
                    label: "No intervention",
                    score: evaluation.no_intervention_simulation.total_weighted_service_person_minutes,
                    selected: false,
                  },
                  ...evaluation.optimization.baseline_comparisons
                    .filter((item) => item.baseline !== "no_intervention")
                    .map((item) => ({
                      key: item.baseline,
                      label: item.baseline === "static_priority" ? "Static priority" : "Greedy",
                      score: item.plan.objective.weighted_service_person_minutes,
                      selected: false,
                    })),
                  {
                    key: "optimized",
                    label: "LIFELINE exact",
                    score: evaluation.optimization.selected_plan.objective.weighted_service_person_minutes,
                    selected: true,
                  },
                ].map((item) => {
                  const peak = Math.max(
                    1,
                    evaluation.optimization.best_primary_score,
                    evaluation.no_intervention_simulation.total_weighted_service_person_minutes,
                  );
                  return (
                    <div className={`comparison-row ${item.selected ? "comparison-selected" : ""}`} key={item.key}>
                      <span className="comparison-label">{item.label}{item.selected && <small>RECOMMENDED</small>}</span>
                      <div className="comparison-track"><span style={{ width: `${(item.score / peak) * 100}%` }} /></div>
                      <strong>{formatNumber(item.score)}</strong>
                    </div>
                  );
                })}
                <p className="comparison-footnote">
                  Every plan uses the same scenario, resources, horizon, and simulator. Scores are modeled service exposure—not lives saved.
                </p>
              </div>
            ) : <div className="map-placeholder">{loading ? "Calculating alternatives…" : "Comparison appears after evaluation."}</div>}
          </section>

          <section className="panel impact-panel">
            <div className="panel-heading">
              <div><span className="panel-kicker">MODELED NEEDS</span><h2>Community service outcomes</h2></div>
              <span className="unit-note">recommended plan</span>
            </div>
            {evaluation ? (
              <div className="impact-list">
                {evaluation.optimization.selected_plan.demand_metrics.map((metric) => (
                  <div className="impact-row" key={metric.demand_id}>
                    <div className="impact-name">
                      <span className={`service-icon service-${metric.service_type}`}><Icon name={metric.service_type === "water" ? "drop" : "air"} /></span>
                      <div><strong>{metric.community_id.replaceAll("-", " ")}</strong><span>{metric.service_type} · {formatNumber(metric.population)} modeled people</span></div>
                    </div>
                    <div className="impact-coverage">
                      <strong>{(metric.coverage_parts_per_million / 10_000).toFixed(1)}<small>%</small></strong>
                      <div><span style={{ width: `${metric.coverage_parts_per_million / 10_000}%` }} /></div>
                      <small>{formatNumber(metric.service_person_minutes)} / {formatNumber(metric.total_service_person_minutes)} person-service-min</small>
                    </div>
                  </div>
                ))}
              </div>
            ) : <div className="map-placeholder">Demand outcomes appear after evaluation.</div>}
          </section>
        </div>

        <section className="panel controls-panel" aria-labelledby="conditions-heading">
          <div className="controls-heading">
            <div><span className="panel-kicker">WHAT IF</span><h2 id="conditions-heading">Change the response conditions</h2></div>
            <button className="secondary-button" type="button" onClick={recalculate} disabled={loading || !scenario}>
              {loading ? "Evaluating…" : resultsStale ? "Apply changes & recompute" : "Recompute current plan"}
            </button>
          </div>
          <div className="controls-grid">
            <div className="control-block">
              <h3>Available response teams</h3>
              <p>Unavailable teams are removed from the candidate assignment space.</p>
              {baseScenario?.resources.length ? baseScenario.resources.map((resource) => (
                <label className="resource-toggle" key={resource.id}>
                  <span><strong>{resource.name}</strong><small>{resource.capabilities.join(" · ")}</small></span>
                  <input
                    type="checkbox"
                    checked={availableResourceIds.includes(resource.id)}
                    onChange={(event) => setResourceAvailable(resource.id, event.target.checked)}
                    aria-label={`${resource.name} available`}
                    disabled={loading}
                  />
                </label>
              )) : <p className="empty-control">This scenario has no dispatchable resources.</p>}
            </div>
            <div className="control-block">
              <h3>Travel time</h3>
              <p>Minutes before backup support can satisfy a dependency group.</p>
              {baseScenario && scenario ? baseScenario.resources.flatMap((resource) => resource.travel_times.map((route) => (
                <label className="travel-control" key={`${resource.id}-${route.asset_id}`}>
                  <span>{resource.name}<small>→ {scenario.assets.find((asset) => asset.id === route.asset_id)?.name ?? route.asset_id}</small></span>
                  <input
                    type="number"
                    min={0}
                    max={Math.max(0, scenario.horizon_minutes - route.setup_minutes - 1)}
                    value={scenario?.resources.find((item) => item.id === resource.id)?.travel_times.find((item) => item.asset_id === route.asset_id)?.travel_minutes ?? route.travel_minutes}
                    onChange={(event) => updateTravelTime(resource.id, route.asset_id, Math.max(0, Number(event.target.value)))}
                    aria-label={`${resource.name} travel minutes to ${route.asset_id}`}
                    disabled={loading}
                  />
                  <small>min</small>
                </label>
              ))) : null}
            </div>
            <div className="control-block tolerance-control">
              <h3>Fairness tolerance</h3>
              <p>Maximum permitted loss from the best primary score before coverage breaks ties.</p>
              <label htmlFor="fairness-tolerance" className="tolerance-value">{(tolerancePpm / 10_000).toFixed(0)}% <span>relative score tolerance</span></label>
              <input
                id="fairness-tolerance"
                type="range"
                min={0}
                max={500_000}
                step={50_000}
                value={tolerancePpm}
                onChange={(event) => {
                  markInputsDirty();
                  setTolerancePpm(Number(event.target.value));
                }}
                disabled={loading}
              />
              <span className="control-hint">Among eligible plans, maximize minimum coverage across explicit demand records.</span>
            </div>
          </div>
        </section>

        <ReceiptInspector
          className={resultsStale ? "results-stale" : ""}
          evaluation={evaluation}
          verification={verification}
          verifying={verifying}
          stale={resultsStale}
          scenarioName={choice?.name ?? scenario?.id ?? "selected scenario"}
          onVerify={verifyReceipt}
        />

        <footer className="footer">
          <div><span className="footer-mark" /> LIFELINE <span className="footer-divider">/</span> DECISION SUPPORT PROTOTYPE</div>
          <span>Deterministic model · Synthetic scenarios · Not an operational recommendation</span>
        </footer>
      </div>
    </main>
  );
}

function RecommendationInsight({
  scenario,
  evaluation,
}: {
  scenario: Scenario;
  evaluation: Evaluation;
}) {
  const plan = evaluation.optimization.selected_plan;
  const complementaryAssignments = new Map<
    string,
    Array<{ groupId: string; description: string }>
  >();
  for (const action of plan.interventions) {
    const asset = scenario.assets.find((item) => item.id === action.target_asset_id);
    const group = asset?.dependency_groups.find(
      (item) => item.id === action.dependency_group_id,
    );
    const resource = scenario.resources.find((item) => item.id === action.resource_id);
    if (!asset || !group || !resource) continue;
    const assignment = {
      groupId: group.id,
      description: `${resource.name} covers the ${group.service_type} input`,
    };
    complementaryAssignments.set(asset.id, [
      ...(complementaryAssignments.get(asset.id) ?? []),
      assignment,
    ]);
  }
  const sharedTarget = [...complementaryAssignments.entries()].find(([, assignments]) =>
    new Set(assignments.map((assignment) => assignment.groupId)).size > 1,
  );
  const sharedAsset = sharedTarget
    ? scenario.assets.find((asset) => asset.id === sharedTarget[0])
    : undefined;
  const explanation = sharedAsset && sharedTarget
    ? `Separate crews cover different inputs to ${sharedAsset.name}: ${sharedTarget[1]
      .filter((assignment, index, assignments) =>
        assignments.findIndex((item) => item.groupId === assignment.groupId) === index,
      )
      .map((assignment) => assignment.description)
      .join("; ")}.`
    : "The selected plan follows the declared service objective and fairness policy.";
  const comparisons = evaluation.optimization.baseline_comparisons.filter(
    (item) => item.baseline === "static_priority" || item.baseline === "greedy",
  );
  const baselineNames = comparisons.map((item) =>
    item.baseline === "static_priority" ? "static-priority" : "greedy",
  );
  const improvedServices = [
    ...new Set(
      plan.demand_metrics
        .filter((metric) =>
          comparisons.length > 0 &&
          comparisons.every((comparison) => {
            const baselineMetric = comparison.plan.demand_metrics.find(
              (item) => item.demand_id === metric.demand_id,
            );
            return baselineMetric !== undefined &&
              metric.service_person_minutes > baselineMetric.service_person_minutes;
          }),
        )
        .map((metric) => metric.service_type),
    ),
  ];
  const serviceImpact = improvedServices.length > 0
    ? ` Modeled service delivery for ${improvedServices.join(" and ")} is higher than in the ${baselineNames.join(" and ")} plans.`
    : "";

  return (
    <section className="recommendation-insight" aria-label="Why this plan">
      <span className="panel-kicker">WHY THIS PLAN</span>
      <p>{explanation}{serviceImpact}</p>
      <div className="insight-comparisons">
        {comparisons.map((item) => (
          <div key={item.baseline}>
            <span>vs {item.baseline === "static_priority" ? "static priority" : "greedy"}</span>
            <strong>{formatSigned(item.primary_score_delta)} wSPM</strong>
          </div>
        ))}
      </div>
      <small>Backend-computed score difference under this synthetic model.</small>
    </section>
  );
}

function formatSigned(value: number) {
  if (value > 0) return `+${formatNumber(value)}`;
  if (value < 0) return `−${formatNumber(Math.abs(value))}`;
  return "0";
}

function DependencyMap({
  assets,
  step,
  demands,
  selectedPlan,
  planLabel,
  loading,
}: {
  assets: Asset[];
  step: TimeStep;
  demands: Scenario["demands"];
  selectedPlan: Plan | undefined;
  planLabel: string;
  loading: boolean;
}) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasWidth, setCanvasWidth] = useState(780);
  useLayoutEffect(() => {
    const element = canvasRef.current;
    if (!element) return;
    const measure = () => {
      const width = Math.round(element.getBoundingClientRect().width);
      if (width > 0) setCanvasWidth(width);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(measure);
    observer?.observe(element);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  const layout = useMemo(
    () => layoutAssets(assets, canvasWidth),
    [assets, canvasWidth],
  );
  const states = new Map(step.assets.map((state) => [state.asset_id, state]));
  const edgeList = assets.flatMap((asset) =>
    asset.dependency_groups.flatMap((group) =>
      group.provider_asset_ids.map((providerId) => ({
        key: `${providerId}-${group.id}`,
        providerId,
        targetId: asset.id,
        groupId: group.id,
        service: group.service_type,
      })),
    ),
  );
  const demandAssets = new Set(demands.map((demand) => demand.served_by_asset_id));
  const activeInterventionIds = new Set(step.active_intervention_ids);

  return (
    <div
      ref={canvasRef}
      className={`network-canvas ${loading ? "network-loading" : ""}`}
      role="img"
      aria-label={`Infrastructure dependency graph for ${planLabel} at minute ${step.minute}`}
      data-orientation={layout.orientation}
    >
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="presentation"
        preserveAspectRatio="xMidYMin meet"
      >
        <defs>
          <marker id="arrow-tip" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" />
          </marker>
        </defs>
        <g className="edge-layer">
          {edgeList.map((edge, edgeIndex) => {
            const from = layout.positions.get(edge.providerId);
            const to = layout.positions.get(edge.targetId);
            const providerState = states.get(edge.providerId);
            if (!from || !to) return null;
            const edgeState = providerState?.physical_fault_active
              ? "faulted"
              : !providerState?.service_available
                ? "failed"
                : providerState.unsatisfied_dependency_group_ids.length
                  ? "buffered"
                  : "active";
            let path: string;
            if (layout.orientation === "horizontal") {
              const x1 = from.x + layout.nodeWidth / 2;
              const x2 = to.x - layout.nodeWidth / 2;
              const curve = Math.max(18, (x2 - x1) * 0.42);
              path = `M ${x1} ${from.y} C ${x1 + curve} ${from.y}, ${x2 - curve} ${to.y}, ${x2} ${to.y}`;
            } else {
              const x1 = from.x + layout.nodeWidth / 2;
              const x2 = to.x + layout.nodeWidth / 2;
              const lane = layout.width - 8 - (edgeIndex % 4) * 8;
              path = `M ${x1} ${from.y} C ${lane} ${from.y + 22}, ${lane} ${to.y - 22}, ${lane} ${to.y} L ${x2} ${to.y}`;
            }
            return (
              <g key={edge.key} className={`edge-group edge-${edgeState}`}>
                <title>{`${edge.service}: ${edge.providerId} to ${edge.targetId}`}</title>
                <path d={path} markerEnd="url(#arrow-tip)" />
                {layout.orientation === "horizontal" && (
                  <text
                    x={(from.x + to.x) / 2}
                    y={(from.y + to.y) / 2 - 7}
                  >
                    {edge.service}
                  </text>
                )}
              </g>
            );
          })}
        </g>
        <g className="node-layer">
          {assets.map((asset) => {
            const position = layout.positions.get(asset.id);
            const state = states.get(asset.id);
            if (!position || !state) return null;
            const backupServices = selectedPlan?.interventions
              .filter((action) =>
                action.target_asset_id === asset.id &&
                activeInterventionIds.has(action.id),
              )
              .map((action) =>
                asset.dependency_groups.find(
                  (group) => group.id === action.dependency_group_id,
                )?.service_type,
              )
              .filter((service): service is string => Boolean(service))
              .filter((service, index, all) => all.indexOf(service) === index) ?? [];
            const status = state.physical_fault_active
              ? "faulted"
              : !state.service_available
                ? "offline"
                : backupServices.length
                  ? "backup"
                  : state.unsatisfied_dependency_group_ids.length
                    ? "buffered"
                    : "online";
            const statusLabel = status === "faulted"
              ? "PHYSICAL FAULT"
              : status === "offline"
                ? "SERVICE UNAVAILABLE"
                : status === "backup"
                  ? `TEMP BACKUP · ${backupServices.join(" + ")}`
                  : status === "buffered"
                    ? `RESERVE · ${state.buffer_units} ${asset.buffer.unit}`
                    : "SERVICE WORKING";
            const inputs = [
              ...new Set(asset.dependency_groups.map((group) => group.service_type)),
            ];
            const nameLines = wrapAssetName(
              asset.name,
              Math.max(15, Math.floor((layout.nodeWidth - 24) / 7.2)),
            );
            const nameTop = -8 - (nameLines.length - 1) * 7;
            return (
              <g
                key={asset.id}
                transform={`translate(${position.x}, ${position.y})`}
                className={`asset-node node-${status}`}
              >
                <rect
                  x={-layout.nodeWidth / 2}
                  y={-layout.nodeHeight / 2}
                  width={layout.nodeWidth}
                  height={layout.nodeHeight}
                  rx="9"
                />
                <circle
                  className="node-indicator"
                  cx={-layout.nodeWidth / 2 + 13}
                  cy={-layout.nodeHeight / 2 + 14}
                  r="4"
                />
                <text
                  className="node-kind"
                  x={-layout.nodeWidth / 2 + 23}
                  y={-layout.nodeHeight / 2 + 18}
                >
                  {asset.kind.replaceAll("_", " ")}
                </text>
                <text className="node-name" x="0" y={nameTop} textAnchor="middle">
                  {nameLines.map((line, index) => (
                    <tspan key={`${asset.id}-name-${index}`} x="0" dy={index ? 14 : 0}>
                      {line}
                    </tspan>
                  ))}
                </text>
                {inputs.length > 0 && (
                  <text className="node-inputs" x="0" y={layout.nodeHeight / 2 - 23} textAnchor="middle">
                    INPUTS · {inputs.join(" + ")}
                  </text>
                )}
                <text
                  className="node-status"
                  x="0"
                  y={layout.nodeHeight / 2 - 8}
                  textAnchor="middle"
                >
                  {statusLabel}
                </text>
                {demandAssets.has(asset.id) && (
                  <circle
                    className="demand-ring"
                    cx={layout.nodeWidth / 2 - 13}
                    cy={-layout.nodeHeight / 2 + 14}
                    r="5"
                  />
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

export function layoutAssets(assets: Asset[], width: number) {
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const levels = new Map<string, number>();
  const levelOf = (asset: Asset, visiting = new Set<string>()): number => {
    const cached = levels.get(asset.id);
    if (cached !== undefined) return cached;
    if (visiting.has(asset.id)) return 0;
    const nextVisiting = new Set(visiting).add(asset.id);
    const providers = asset.dependency_groups.flatMap((group) =>
      group.provider_asset_ids.map((id) => byId.get(id)).filter((item): item is Asset => Boolean(item)),
    );
    const level = providers.length
      ? Math.max(...providers.map((provider) => levelOf(provider, nextVisiting))) + 1
      : 0;
    levels.set(asset.id, level);
    return level;
  };
  assets.forEach((asset) => levelOf(asset));
  const byLevel = new Map<number, Asset[]>();
  for (const asset of assets) {
    const level = levels.get(asset.id) ?? 0;
    byLevel.set(level, [...(byLevel.get(level) ?? []), asset]);
  }
  const maxLevel = Math.max(0, ...levels.values());
  const nodeHeight = 104;
  const positions = new Map<string, { x: number; y: number; level: number; row: number }>();
  if (width >= 700) {
    const nodeWidth = 210;
    const margin = 14;
    const levelCount = maxLevel + 1;
    const columnStep = levelCount > 1
      ? (width - margin * 2 - nodeWidth) / maxLevel
      : 0;
    let maxRows = 1;
    for (const [level, items] of byLevel) {
      maxRows = Math.max(maxRows, items.length);
      items.forEach((asset, row) => {
        positions.set(asset.id, {
          x: levelCount > 1 ? margin + nodeWidth / 2 + level * columnStep : width / 2,
          y: 60 + row * 132,
          level,
          row,
        });
      });
    }
    return {
      orientation: "horizontal" as const,
      width,
      height: 60 + maxRows * 132,
      nodeWidth,
      nodeHeight,
      positions,
    };
  }

  const nodeWidth = Math.max(160, width - 72);
  const orderedAssets = [...assets].sort(
    (left, right) => (levels.get(left.id) ?? 0) - (levels.get(right.id) ?? 0),
  );
  orderedAssets.forEach((asset, row) => {
    positions.set(asset.id, {
      x: width / 2,
      y: 60 + row * 138,
      level: levels.get(asset.id) ?? 0,
      row,
    });
  });
  return {
    orientation: "vertical" as const,
    width,
    height: 60 + orderedAssets.length * 138,
    nodeWidth,
    nodeHeight,
    positions,
  };
}

function wrapAssetName(value: string, maxCharacters: number) {
  const lines: string[] = [];
  let line = "";
  for (const word of value.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (line && next.length > maxCharacters) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function ReceiptInspector({
  className,
  evaluation,
  verification,
  verifying,
  stale,
  scenarioName,
  onVerify,
}: {
  className: string;
  evaluation: Evaluation | null;
  verification: VerificationReport | null;
  verifying: boolean;
  stale: boolean;
  scenarioName: string;
  onVerify: (receipt: Receipt) => void;
}) {
  const exhaustiveSearch = evaluation?.receipt.payload.search.exhaustive_search_complete ?? false;

  return (
    <section className={`panel receipt-panel ${className}`}>
      <div className="receipt-heading">
        <div><span className="panel-kicker">REPRODUCIBILITY</span><h2>Decision Receipt</h2></div>
        {evaluation && <span className="digest-label"><span className="digest-dot" /> SHA-256 · {evaluation.receipt.integrity.digest.slice(0, 12)}…</span>}
      </div>
      {evaluation ? (
        <>
          <div className="receipt-explanation">
            <p>
              Evaluated {formatNumber(evaluation.receipt.payload.search.plans_evaluated)} candidate plans for <strong>{scenarioName}</strong>.
              The selected plan follows the recorded objective and fairness policy.
            </p>
            <p>
              Verification checks the receipt, inputs, replay, baselines, and bounded search.
              A pass confirms agreement with this model; it does not prove physical accuracy or operational safety.
            </p>
          </div>
          <div className="receipt-summary">
            <div><span>SCHEMA</span><strong>1.0</strong></div>
            <div>
              <span>SEARCH</span>
              <strong>
                {formatNumber(evaluation.receipt.payload.search.plans_evaluated)} plans · {exhaustiveSearch ? "exhaustive" : "bound reached"}
              </strong>
            </div>
            <div><span>BEST PRIMARY SCORE</span><strong>{formatNumber(evaluation.receipt.payload.search.best_primary_score)} wSPM</strong></div>
            <div><span>SELECTED SCORE</span><strong>{formatNumber(evaluation.receipt.payload.search.selected_primary_score)} wSPM</strong></div>
          </div>
          <div className="receipt-actions">
            <button className="secondary-button" type="button" onClick={() => onVerify(evaluation.receipt)} disabled={verifying || stale}>
              {verifying ? <><span className="spinner" /> Verifying receipt…</> : <><Icon name="shield" /> Verify this decision</>}
            </button>
            {stale && <span className="receipt-stale-label">Recompute before verifying this receipt.</span>}
            <details className="receipt-details">
              <summary>Inspect receipt payload</summary>
              <pre>{JSON.stringify(evaluation.receipt, null, 2)}</pre>
            </details>
          </div>
          {verification && (
            <div className={`verification-result ${verification.valid ? "verification-valid" : "verification-invalid"}`} aria-live="polite">
              <div className="verification-title">
                <span className="verify-mark"><Icon name={verification.valid ? "check" : "warning"} /></span>
                <div><strong>{verification.valid ? "Receipt verified" : "Verification found issues"}</strong><span>{verification.valid ? "Replay, reported outcomes, baselines, and bounded optimality agree with the declared model." : `${verification.issues.length} issue${verification.issues.length === 1 ? "" : "s"} reported.`}</span></div>
              </div>
              <ul className="verification-checks">
                {CHECKS.map(([key, label]) => {
                  const status = verification[key];
                  return <li key={key}><span className={`check-dot check-${status}`} />{label}<strong>{status.replaceAll("_", " ")}</strong></li>;
                })}
              </ul>
              {verification.issues.length > 0 && (
                <ul className="verification-issues">
                  {verification.issues.map((issue, index) => <li key={`${issue.code}-${index}`}><strong>{issue.code}</strong> {issue.message}</li>)}
                </ul>
              )}
            </div>
          )}
          <div className="assumptions">
            <div>
              <span className="panel-kicker">MODEL ASSUMPTIONS</span>
              <ul>{evaluation.receipt.payload.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
            <div>
              <span className="panel-kicker">LIMITATIONS</span>
              <ul>{evaluation.receipt.payload.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </div>
        </>
      ) : <div className="map-placeholder">A receipt is generated after the scenario is evaluated.</div>}
    </section>
  );
}

function Icon({ name }: { name: string }) {
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true as const };
  switch (name) {
    case "bolt": return <svg {...common}><path d="m13 2-3 9h7l-6 11 2-9H6z" /></svg>;
    case "check": return <svg {...common}><path d="m5 12 4 4L19 6" /></svg>;
    case "arrow": return <svg {...common}><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
    case "branch": return <svg {...common}><circle cx="6" cy="6" r="2" /><circle cx="18" cy="18" r="2" /><path d="M8 6h2a4 4 0 0 1 4 4v4a4 4 0 0 0 4 4" /></svg>;
    case "refresh": return <svg {...common}><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.5 9a7 7 0 0 1 11.6-2.6L20 12M4 12l2.9 5.6A7 7 0 0 0 18.5 15" /></svg>;
    case "play": return <svg {...common} fill="currentColor" stroke="none"><path d="m8 5 11 7-11 7z" /></svg>;
    case "pause": return <svg {...common} fill="currentColor" stroke="none"><path d="M7 5h4v14H7zM14 5h4v14h-4z" /></svg>;
    case "drop": return <svg {...common}><path d="M12 3s6 6.4 6 11a6 6 0 0 1-12 0c0-4.6 6-11 6-11Z" /><path d="M9 15a3 3 0 0 0 3 3" /></svg>;
    case "air": return <svg {...common}><path d="M3 8h12a3 3 0 1 0-3-3M2 12h17a3 3 0 1 1-3 3M5 16h7a2 2 0 1 1-2 2" /></svg>;
    case "shield": return <svg {...common}><path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6z" /><path d="m9 12 2 2 4-4" /></svg>;
    case "warning": return <svg {...common}><path d="M12 3 2.8 19h18.4L12 3Z" /><path d="M12 9v4m0 3h.01" /></svg>;
    default: return null;
  }
}

export default App;
