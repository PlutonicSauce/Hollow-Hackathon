import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api } from "./api";
import { CoordinationExplorer } from "./CoordinationExplorer";
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
  optimized: "Recommended response",
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
  const [availableResourceIds, setAvailableResourceIds] = useState<string[]>(
    [],
  );
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [planKey, setPlanKey] = useState<PlanKey>("optimized");
  const [minute, setMinute] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");
  const [errorOperation, setErrorOperation] = useState<"evaluate" | "verify">("evaluate");
  const [verification, setVerification] = useState<VerificationReport | null>(
    null,
  );
  const [tolerancePpm, setTolerancePpm] = useState(0);
  const [resultsStale, setResultsStale] = useState(false);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [pendingChange, setPendingChange] = useState<
    { kind: "recompute" } | { kind: "scenario"; key: string } | null
  >(null);
  const reviewDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (pendingChange && !reviewDialog.current?.open)
      reviewDialog.current?.showModal();
  }, [pendingChange]);
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
      setErrorOperation("evaluate");
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
          setError(
            reason instanceof Error
              ? reason.message
              : "The scenario could not be evaluated.",
          );
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
        if (active)
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load scenarios.",
          );
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
    setErrorOperation("evaluate");
    api
      .scenario(scenarioKey)
      .then(async (loaded) => {
        if (!active) return;
        setBaseScenario(loaded);
        setScenario(loaded);
        setAvailableResourceIds(
          loaded.resources.map((resource) => resource.id),
        );
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
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load the incident.",
          );
        }
      })
      .finally(() => {
        if (active && requestId === evaluationRequest.current)
          setLoading(false);
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

  useEffect(() => {
    if (!playing || !evaluation) return;
    const timer = window.setInterval(() => {
      setMinute((current) => {
        if (current >= evaluation.scenario.horizon_minutes) {
          setPlaying(false);
          return current;
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
    setSelectedAssetId("");
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
    setError("");
    setErrorOperation("evaluate");
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
    const resources = baseScenario.resources.filter((resource) =>
      ids.has(resource.id),
    );
    const updated = { ...baseScenario, resources, interventions: [] };
    setScenario(updated);
    setVerification(null);
  };

  const updateTravelTime = (
    resourceId: string,
    assetId: string,
    minutes: number,
  ) => {
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
    if (scenario && resultsStale) setPendingChange({ kind: "recompute" });
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
        setError(
          reason instanceof Error
            ? reason.message
            : "Receipt verification failed.",
        );
        setErrorOperation("verify");
      }
    } finally {
      if (requestId === verificationRequest.current) setVerifying(false);
    }
  };

  const displayScenario = evaluation?.scenario ?? scenario;
  const linkedAssets = useMemo(
    () => relatedAssets(displayScenario?.assets ?? [], selectedAssetId),
    [displayScenario, selectedAssetId],
  );
  const inspectedAsset = displayScenario?.assets.find(
    (asset) => asset.id === selectedAssetId,
  );
  const recommended = evaluation?.optimization.selected_plan;
  const bestBaseline = Math.max(
    0,
    ...(evaluation?.optimization.baseline_comparisons.map(
      (item) => item.plan.objective.weighted_service_person_minutes,
    ) ?? [0]),
  );
  const score = recommended?.objective.weighted_service_person_minutes ?? 0;
  const planOptions = evaluation
    ? [
        {
          key: "no_intervention" as PlanKey,
          label: "No response",
          score:
            evaluation.no_intervention_simulation
              .total_weighted_service_person_minutes,
          description: "Let reserves and dependencies run without backup.",
        },
        ...evaluation.optimization.baseline_comparisons
          .filter((item) => item.baseline !== "no_intervention")
          .map((item) => ({
            key: item.baseline as PlanKey,
            label: PLAN_LABELS[item.baseline as PlanKey],
            score: item.plan.objective.weighted_service_person_minutes,
            description:
              item.baseline === "greedy"
                ? "Choose the strongest immediate gain, one crew at a time."
                : "Prioritize direct demand at each destination.",
          })),
        {
          key: "optimized" as PlanKey,
          label: "Recommended",
          score,
          description: evaluation.optimization.exhaustive_search_complete
            ? "Every feasible assignment in this supported search was evaluated."
            : "Search incomplete. This result is not a proven optimum.",
        },
      ]
    : [];
  const changedInputs = describeChanges(
    evaluation?.scenario,
    scenario,
    evaluation?.optimization.policy.primary_tolerance_ppm ?? 0,
    tolerancePpm,
  );

  const disruptedServices = [
    ...new Set(
      evaluation?.no_intervention_simulation.demand_metrics
        .filter((metric) => metric.coverage_parts_per_million < 1_000_000)
        .map((metric) => metric.service_type) ?? [],
    ),
  ];
  const availableServices = displayScenario?.demands.filter((demand) => currentStep?.assets.find((asset) => asset.asset_id === demand.served_by_asset_id)?.service_available).length ?? 0;
  const atEndBoundary = Boolean(evaluation && minute === displayScenario?.horizon_minutes);
  const backupEnded = atEndBoundary && Boolean(trace[minute - 1]?.active_intervention_ids.length && !currentStep?.active_intervention_ids.length);
  const replayPhase = !evaluation ? "Preparing simulation" : minute === 0 ? "Initial state · Minute 0" : minute >= (displayScenario?.horizon_minutes ?? 0) ? "End of modeled window" : planKey === "no_intervention" ? "Without a response" : "Response underway";
  const incidentTitle = disruptedServices.length
    ? `${disruptedServices.join(" and ").replace(/^./, (char) => char.toUpperCase())} services face disruption.`
    : "Essential services need a response.";
  return (
    <main className={`app-shell ${playing ? "is-playing" : ""}`}>
      <header className="topbar">
        <a className="brand" href="#" aria-label="LIFELINE home">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          LIFELINE
        </a>
        <span className="product-category">Infrastructure resilience</span>
        <nav className="workspace-nav" aria-label="Workspace">
          <a href="#network">Explore</a>
          <a href="#response">Response</a>
          <a href="#decision-audit">Decision audit</a>
        </nav>
        <div className="topbar-right">
          <label htmlFor="scenario-select">Scenario</label>
          <select
            id="scenario-select"
            aria-label="Active scenario"
            value={scenarioKey}
            onChange={(event) => {
              if (resultsStale)
                setPendingChange({ kind: "scenario", key: event.target.value });
              else changeScenario(event.target.value);
            }}
            disabled={loading}
          >
            {choices.length ? (
              choices.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.name}
                </option>
              ))
            ) : (
              <option value="coupled-utility">Coupled utility failure</option>
            )}
          </select>
        </div>
      </header>
      <div className="content">
        <section className="incident-header" aria-labelledby="incident-title">
          <p className="incident-kicker">
            {choice?.name ?? "Coupled utility failure"} · Synthetic scenario
          </p>
          <h1 id="incident-title">{incidentTitle}</h1>
          <div className="incident-context">
            <p>
              <span className="incident-failure">
                <Icon name="warning" /> What failed
              </span>
              {displayScenario?.faults
                .map((fault) =>
                  humanAssetName(
                    displayScenario.assets.find(
                      (asset) => asset.id === fault.asset_id,
                    )?.name ?? fault.id,
                  ),
                )
                .join(" and ") || "Loading the incident…"}{" "}
              offline.
            </p>
            <p>
              <span className="incident-failure">Who is affected</span>
              {displayScenario?.demands
                .map(
                  (demand) =>
                    `${demand.community_id.replaceAll("-", " ")}: ${demand.service_type} for ${formatNumber(demand.population)} modeled people`,
                )
                .join(" · ")}
            </p>
          </div>
        </section>

        <div className="run-status" role="status" aria-live="polite">
          <span className={loading ? "status-working" : ""}>
            {loading
              ? scenario
                ? "Comparing response options…"
                : "Loading the scenario…"
              : resultsStale
                ? "Inputs have changed"
                : evaluation
                  ? evaluation.optimization.exhaustive_search_complete
                    ? "Response ready to explore"
                    : "Search incomplete"
                  : "Ready to evaluate"}
          </span>
          <span>
            {loading
              ? "Results appear when computation completes."
              : resultsStale
                ? "Showing the previous run until you confirm and recompute."
                : evaluation
                  ? `${displayScenario?.horizon_minutes ?? "—"} minute replay · Synthetic inputs`
                  : ""}
          </span>
        </div>
        {error && (
          <div className="error-banner" role="alert">
            <div>
              <strong>That action could not be completed</strong>
              <p>{error}</p>
            </div>
            <button
              type="button"
              className="secondary-button"
              disabled={loading || verifying || (errorOperation === "verify" && resultsStale)}
              onClick={() =>
                errorOperation === "verify" && evaluation
                  ? void verifyReceipt(evaluation.receipt)
                  : resultsStale
                  ? recalculate()
                  : scenario
                    ? void runEvaluation(scenario, tolerancePpm)
                    : window.location.reload()
              }
            >
              {errorOperation === "verify" ? "Retry verification" : "Retry evaluation"}
            </button>
            <button onClick={() => setError("")} aria-label="Dismiss error">
              ×
            </button>
          </div>
        )}

        <div className="experience-grid">
          <section
            id="response"
            className={`response-sheet ${resultsStale ? "results-stale" : ""}`}
            aria-label="Recommended response and comparison"
            aria-busy={loading}
          >
            {evaluation &&
              !evaluation.optimization.exhaustive_search_complete && (
                <p className="search-state">Search incomplete</p>
              )}
            <div className="response-summary">
              <div className="response-eyebrow">
                <span className="response-check">
                  <Icon name="check" />
                </span>{" "}
                Recommended response
              </div>
              <h2>
                {recommended?.interventions.length
                  ? new Set(
                      recommended.interventions.map(
                        (action) => action.target_asset_id,
                      ),
                    ).size === 1
                    ? `Support the ${humanAssetName(displayScenario?.assets.find((asset) => asset.id === recommended.interventions[0].target_asset_id)?.name ?? "shared infrastructure").toLowerCase()}`
                    : "Coordinate the available teams"
                  : evaluation
                    ? "Keep your teams available"
                    : "Finding the right response"}
              </h2>
              <p className="response-intro">
                {evaluation
                  ? recommended?.interventions.length
                    ? `Use ${recommended.interventions.length} ${recommended.interventions.length === 1 ? "team" : "teams"} to cover ${[...new Set(recommended.interventions.map((action) => displayScenario?.assets.find((asset) => asset.id === action.target_asset_id)?.dependency_groups.find((group) => group.id === action.dependency_group_id)?.service_type).filter(Boolean))].join(" and ")} inputs with temporary backup.`
                    : "No supported dispatch improves this scenario’s objective."
                  : "The engine is comparing the supported assignments."}
              </p>
              <details className="dispatch-details">
                <summary>
                  {recommended
                    ? `${recommended.interventions.length} ${recommended.interventions.length === 1 ? "team" : "teams"} · View assignments`
                    : "Response assignments"}
                </summary>
                <div className="dispatch-list">
                  {recommended?.interventions.map((action) => {
                    const resource = displayScenario?.resources.find(
                      (item) => item.id === action.resource_id,
                    );
                    const asset = displayScenario?.assets.find(
                      (item) => item.id === action.target_asset_id,
                    );
                    const route = resource?.travel_times.find(
                      (item) => item.asset_id === action.target_asset_id,
                    );
                    const group = asset?.dependency_groups.find(
                      (item) => item.id === action.dependency_group_id,
                    );
                    return (
                      <button
                        className="dispatch-row"
                        type="button"
                        key={action.id}
                        onClick={() => {
                          setSelectedAssetId(action.target_asset_id);
                          document
                            .getElementById("network")
                            ?.scrollIntoView({ block: "nearest" });
                        }}
                      >
                        <span className="dispatch-symbol">
                          <Icon
                            name={
                              group?.service_type === "water" ? "drop" : "bolt"
                            }
                          />
                        </span>
                        <span>
                          <strong>{resource?.name ?? action.resource_id}</strong>
                          <span>{asset?.name ?? action.target_asset_id}</span>
                          <small>
                            {group?.service_type} backup · arrives at minute{" "}
                            {action.dispatch_minute +
                              (route?.travel_minutes ?? 0) +
                              (route?.setup_minutes ?? 0)}
                          </small>
                        </span>
                        <Icon name="arrow" />
                      </button>
                    );
                  })}
                </div>
              </details>
            </div>
            <div className="benefit-block">
              <span>Modeled outcome · full {displayScenario?.horizon_minutes ?? "—"} minutes</span>
              <strong>
                {evaluation
                  ? bestBaseline > 0 && score > bestBaseline
                    ? `${Math.round(((score - bestBaseline) / bestBaseline) * 100)}% higher service score`
                    : score > bestBaseline
                      ? "More modeled service restored"
                      : "Best result under this policy"
                  : "Comparing outcomes…"}
              </strong>
              <p>Against the strongest baseline, with the same resources.</p>
              <div className="exact-score">
                <span>
                  <b>{evaluation ? formatNumber(score) : "—"}</b> recommended
                </span>
                <span>vs</span>
                <span>
                  <b>{evaluation ? formatNumber(bestBaseline) : "—"}</b>{" "}
                  baseline
                </span>
              </div>
              <small>weighted service-person-minutes · not lives saved</small>
              <p className="score-explanation">People receiving each service × minutes available × its priority weight. A model score, not a count of lives saved.</p>
            </div>
            <div className="response-tools">
              <button
                className="primary-button watch-recovery"
                disabled={!evaluation || loading || resultsStale}
                onClick={() => {
                  setPlanKey("optimized");
                  setMinute(0);
                  setPlaying(true);
                  document.getElementById("network")?.scrollIntoView({ block: "start" });
                }}
              >
                <Icon name="play" />Watch recovery
              </button>
              <details className="compare-details">
                <summary>
                  Compare all responses <Icon name="branch" />
                </summary>
                <p>Select a response to see what changes on the map.</p>
                {planOptions.map((option) => (
                  <button
                    type="button"
                    className="baseline-line"
                    key={option.key}
                    aria-pressed={planKey === option.key}
                    onClick={() => {
                      setPlanKey(option.key);
                      setPlaying(false);
                    }}
                  >
                    <span>{option.label}</span>
                    <strong>{formatNumber(option.score)}</strong>
                    <span className="comparison-track">
                      <span
                        style={{
                          width: `${(option.score / Math.max(1, ...planOptions.map((item) => item.score))) * 100}%`,
                        }}
                      />
                    </span>
                    <small>{option.description}</small>
                  </button>
                ))}
              </details>
              <a className="audit-shortcut" href="#decision-audit">
                <Icon name="shield" />
                <span>
                  <strong>
                    {verification?.valid && !resultsStale
                      ? "Decision verified"
                      : "Check this decision"}
                  </strong>
                  <small>Replay, alternatives and receipt integrity</small>
                </span>
                <Icon name="arrow" />
              </a>
              {evaluation?.coordination_certificate && (
                <a className="coordination-link" href="#coordination">Explore each action’s contribution →</a>
              )}
              <details className="response-more"><summary>Coverage & reasoning</summary>
              <details className="coverage-details">
                <summary>Community coverage · full simulation</summary>
                <p className="section-note">Viewing {PLAN_LABELS[planKey]}</p>
                {selectedPlan?.demand_metrics.map((metric) => (
                  <div className="impact-row" key={metric.demand_id}>
                    <span>
                      <strong>{metric.community_id.replaceAll("-", " ")}</strong>
                      <small>{metric.service_type}</small>
                    </span>
                    <strong>
                      {(metric.coverage_parts_per_million / 10000).toFixed(1)}%
                    </strong>
                  </div>
                ))}
              </details>
              <details className="method-details">
                <summary>Why this response?</summary>
                {evaluation && (
                  <RecommendationInsight
                    scenario={evaluation.scenario}
                    evaluation={evaluation}
                  />
                )}
                <p>
                  {evaluation?.optimization.exhaustive_search_complete
                    ? `${evaluation.optimization.plans_evaluated} plans checked exhaustively.`
                    : "The result is not established until the search completes."}
                </p>
                <p>
                  Policy weights and coverage tolerance influence the
                  recommendation. Exact search took{" "}
                  {evaluation
                    ? (
                        evaluation.optimization.computation_time_ns / 1_000_000
                      ).toFixed(1)
                    : "—"}{" "}
                  ms on the backend.
                </p>
              </details>
              </details>
            </div>
          </section>
          <section
            className="network-panel"
            id="network"
            aria-labelledby="network-title"
          >
            <div className="map-toolbar">
              {" "}
              <div className="timeline-title">
                <h3>{replayPhase}</h3><p>{PLAN_LABELS[planKey]} · Minute {minute} of {displayScenario?.horizon_minutes ?? "—"}</p>
                <div className="replay-controls">
                  <button
                    type="button"
                    className="play-button"
                    onClick={() => {
                      if (minute >= (displayScenario?.horizon_minutes ?? 0))
                        setMinute(0);
                      setPlaying((value) => !value);
                    }}
                    disabled={!evaluation || loading || resultsStale}
                    aria-label={playing ? "Pause replay" : "Play replay"}
                  >
                    <Icon name={playing ? "pause" : "play"} />
                    <span>{playing ? "Pause" : minute >= (displayScenario?.horizon_minutes ?? 0) ? "Replay" : "Play recovery"}</span>
                  </button>
                </div>
              </div>
              <div className="replay-position"><strong>{availableServices} of {displayScenario?.demands.length ?? 0} community services available</strong><span>{atEndBoundary ? `${backupEnded ? "Temporary backup has ended. " : ""}This endpoint adds no service time; the score covers minutes 0–${Math.max(0, (displayScenario?.horizon_minutes ?? 1) - 1)}.` : minute === 0 ? "Services at the start of the selected plan. The benefit above covers the full simulation." : "Availability at this minute, from the backend trace."}</span></div>
              <div className="scrubber">
                <span>0 min</span>
                <input
                  aria-label="Simulation minute"
                  type="range"
                  min={0}
                  max={displayScenario?.horizon_minutes ?? 1}
                  value={Math.min(
                    minute,
                    displayScenario?.horizon_minutes ?? 0,
                  )}
                  onChange={(event) => {
                    setPlaying(false);
                    setMinute(Number(event.target.value));
                  }}
                  disabled={!evaluation || loading || resultsStale}
                />
                <span>{displayScenario?.horizon_minutes ?? "—"} min</span>
                <output aria-live="off">Minute {minute}</output>
                <button className="time-jump" disabled={!evaluation || loading || resultsStale} onClick={() => {setPlaying(false); setMinute(0);}}>Initial state</button>
                <button className="time-jump" disabled={!evaluation || loading || resultsStale} onClick={() => {setPlaying(false); setMinute(displayScenario?.horizon_minutes ?? 0);}}>End boundary</button>
              </div>
            </div>

            <div className="section-heading">
              <div>
                <h2 id="network-title">
                  {inspectedAsset
                    ? humanAssetName(inspectedAsset.name)
                    : "Infrastructure & community services"}
                </h2>
                <p className="section-note">
                  {inspectedAsset
                    ? inspectedAsset.dependency_groups.length
                      ? `Needs ${inspectedAsset.dependency_groups.map((group) => `${group.service_type} from ${group.provider_asset_ids.map((id) => humanAssetName(displayScenario?.assets.find((asset) => asset.id === id)?.name ?? id)).join(" or ")}`).join(" and ")}.`
                      : `Source supply for ${inspectedAsset.provides}.`
                    : "Follow supply to services. Select an asset to inspect its required inputs."}
                </p>
              </div>
              <span className="viewing-plan">
                {PLAN_LABELS[planKey]} · minute {minute}
              </span>
            </div>

            <div className="network-workspace">
              <div className="map-area">
                {displayScenario ? (
                  <DependencyMap
                    assets={displayScenario.assets}
                    initialStep={trace[0]}
                    step={
                      currentStep ?? {
                        minute: 0,
                        assets: [],
                        active_fault_ids: [],
                        active_intervention_ids: [],
                      }
                    }
                    demands={displayScenario.demands}
                    selectedPlan={selectedPlan}
                    planLabel={PLAN_LABELS[planKey]}
                    loading={loading || resultsStale}
                    playing={playing}
                    selectedAssetId={selectedAssetId}
                    linkedAssets={linkedAssets}
                    onSelect={setSelectedAssetId}
                  />
                ) : (
                  <div className="map-placeholder">Loading infrastructure…</div>
                )}
                <div
                  className="live-consequences"
                  aria-label="Community services at selected minute"
                >
                  {displayScenario?.demands.map((demand) => {
                    const state = currentStep?.assets.find(
                      (item) => item.asset_id === demand.served_by_asset_id,
                    );
                    return (
                      <button
                        type="button"
                        key={demand.id}
                        onClick={() =>
                          setSelectedAssetId(demand.served_by_asset_id)
                        }
                        className={`${!state ? "service-pending" : state.service_available ? "service-available" : "service-unavailable"} ${selectedAssetId && !linkedAssets.has(demand.served_by_asset_id) ? "context-dimmed" : ""}`}
                      >
                        <span>{demand.community_id.replaceAll("-", " ")}</span>
                        <strong>
                          {demand.service_type} ·{" "}
                          {state
                            ? state.service_available
                              ? "available"
                              : "unavailable"
                            : "pending"}
                        </strong>
                        <small>
                          Minute {minute} · {formatNumber(demand.population)}{" "}
                          modeled people
                        </small>
                      </button>
                    );
                  })}
                </div>
                <div className="legend" aria-label="Asset status legend">
                  <span className="connection-key"><i /> Solid: supply available</span>
                  <span className="connection-key connection-unavailable"><i /> Dashed: supply unavailable</span>
                  <span>
                    <i className="legend-good" />
                    Working
                  </span>
                  <span>
                    <i className="legend-warn" />
                    Reserve
                  </span>
                  <span>
                    <i className="legend-backup" />
                    Backup
                  </span>
                  <span>
                    <i className="legend-down" />
                    Unavailable
                  </span>
                  <span>
                    <i className="legend-fault" />
                    Physical fault
                  </span>
                </div>
                <p className="map-caption">
                  Schematic, not geographic. Arrows show required supply relationships, not physical flows.
                </p>
              </div>
            </div>
            <fieldset
              className="plan-switcher"
              disabled={!evaluation || loading}
            >
              <legend className="sr-only">Response plan</legend>
              {planOptions.length
                ? planOptions.map((option) => (
                    <label
                      className={`comparison-row ${planKey === option.key ? "comparison-selected" : ""}`}
                      key={option.key}
                    >
                      <input
                        type="radio"
                        name="response-plan"
                        value={option.key}
                        checked={planKey === option.key}
                        onChange={() => {
                          setPlanKey(option.key);
                          setPlaying(false);
                        }}
                      />
                      <span className="comparison-label">{option.label}</span>
                    </label>
                  ))
                : [
                    "No response",
                    "Static priority",
                    "Greedy response",
                    "Recommended",
                  ].map((label) => (
                    <div
                      className="comparison-row comparison-skeleton"
                      key={label}
                    >
                      <span>{label}</span>
                      <span>—</span>
                    </div>
                  ))}
            </fieldset>
            <aside
              className="asset-inspector"
              aria-label="Selected infrastructure"
            >
              {inspectedAsset && displayScenario ? (
                <>
                  <div className="inspector-heading">
                    <span className="context-label">
                      Selected infrastructure
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedAssetId("")}
                      aria-label="Clear asset selection"
                    >
                      ×
                    </button>
                  </div>
                  <h3>{inspectedAsset.name}</h3>
                  <p>
                    {assetStateLabel(
                      currentStep?.assets.find(
                        (state) => state.asset_id === inspectedAsset.id,
                      ),
                    )}
                  </p>
                  <h4>Required inputs</h4>
                  <p>All input groups are required (AND). Within each group, any listed provider can supply it (OR). Reserves or active backup can temporarily cover missing inputs.</p>
                  <div className="asset-links">
                    {inspectedAsset.dependency_groups.length ? (
                      inspectedAsset.dependency_groups.map((group) => (
                        <div key={group.id}>
                          <small>
                            {group.service_type} ·{" "}
                            {group.provider_asset_ids.length > 1
                              ? "any provider"
                              : "required input"}
                          </small>
                          {group.provider_asset_ids.map((id) => (
                            <button
                              type="button"
                              key={id}
                              onClick={() => setSelectedAssetId(id)}
                            >
                              {displayScenario.assets.find(
                                (asset) => asset.id === id,
                              )?.name ?? id}
                              <small>{currentStep?.assets.find((asset) => asset.asset_id === id)?.service_available ? "Supply available" : "Supply unavailable"}</small>
                              <Icon name="arrow" />
                            </button>
                          ))}
                        </div>
                      ))
                    ) : (
                      <p>No upstream dependency in this model.</p>
                    )}
                  </div>
                  <h4>Consequences downstream</h4>
                  <p>
                    {displayScenario.demands
                      .filter((demand) =>
                        linkedAssets.has(demand.served_by_asset_id),
                      )
                      .map(
                        (demand) =>
                          `${demand.community_id.replaceAll("-", " ")} (${demand.service_type})`,
                      )
                      .join(" · ") || "No explicit community demand connected."}
                  </p>
                  <small>
                    Highlighted paths show structural dependencies, not proof
                    that every connected service is currently down.
                  </small>
                </>
              ) : (
                <>
                  <Icon name="branch" />
                  <h3>Follow a connection</h3>
                  <p>
                    Choose an asset on the map. See what it needs, which
                    communities depend on it, and when its events occur.
                  </p>
                  <p className="inspector-hint">
                    Map selection also highlights connected community services.
                  </p>
                </>
              )}
            </aside>
            <div className="timeline-panel">
              <div className="timeline-events" aria-label="Scenario events">
                {displayScenario?.faults.map((fault) => (
                  <button
                    type="button"
                    className={`timeline-event event-fault ${selectedAssetId && !linkedAssets.has(fault.asset_id) ? "context-dimmed" : ""}`}
                    key={fault.id}
                    disabled={!evaluation}
                    onClick={() => {
                      setSelectedAssetId(fault.asset_id);
                      setMinute(fault.start_minute);
                      setPlaying(false);
                    }}
                  >
                    <span>Minute {fault.start_minute}</span>
                    <strong>
                      {
                        displayScenario.assets.find(
                          (asset) => asset.id === fault.asset_id,
                        )?.name
                      }
                    </strong>
                    <small>
                      Physical failure
                      {fault.end_minute !== null
                        ? ` · ends at minute ${fault.end_minute}`
                        : ""}
                    </small>
                  </button>
                ))}
                {selectedPlan?.interventions.map((action) => {
                  const resource = displayScenario?.resources.find(
                    (item) => item.id === action.resource_id,
                  );
                  const route = resource?.travel_times.find(
                    (item) => item.asset_id === action.target_asset_id,
                  );
                  const arrival =
                    action.dispatch_minute +
                    (route?.travel_minutes ?? 0) +
                    (route?.setup_minutes ?? 0);
                  return (
                    <button
                      type="button"
                      className={`timeline-event event-response ${selectedAssetId && !linkedAssets.has(action.target_asset_id) ? "context-dimmed" : ""}`}
                      key={action.id}
                      onClick={() => {
                        setSelectedAssetId(action.target_asset_id);
                        setMinute(arrival);
                        setPlaying(false);
                      }}
                    >
                      <span>Minute {arrival}</span>
                      <strong>
                        {resource?.name ?? action.resource_id} arrives
                      </strong>
                      <small>
                        Backup at{" "}
                        {
                          displayScenario?.assets.find(
                            (asset) => asset.id === action.target_asset_id,
                          )?.name
                        }
                      </small>
                    </button>
                  );
                })}
              </div>
            </div>
          </section>


        </div>

        {evaluation?.coordination_certificate && (
          <CoordinationExplorer
            key={evaluation.coordination_certificate.certificate_sha256}
            evaluation={evaluation}
            certificate={evaluation.coordination_certificate}
            stale={resultsStale || loading}
          />
        )}

        <ReceiptInspector
          className={resultsStale ? "results-stale" : ""}
          evaluation={evaluation}
          verification={verification}
          verifying={verifying}
          stale={resultsStale}
          scenarioName={choice?.name ?? scenario?.id ?? "selected scenario"}
          onVerify={verifyReceipt}
        />

        <details className="controls-panel">
          <summary>
            <span>
              <strong>Change response conditions</strong>
              <small>Team availability, travel time and coverage policy</small>
            </span>
            <span aria-hidden="true">+</span>
          </summary>
          <section aria-labelledby="conditions-heading">
            <div className="controls-heading">
              <h2 id="conditions-heading">Explore a different response</h2>
              <button
                type="button"
                className="primary-button"
                onClick={recalculate}
                disabled={loading || !scenario || !resultsStale}
              >
                Review changes
              </button>
            </div>
            <p>
              Edits stay in draft. Review and confirm before replacing the
              current result.
            </p>
            <div className="controls-grid">
              <div className="control-block">
                <h3>Available teams</h3>
                {baseScenario?.resources.map((resource) => (
                  <label className="resource-toggle" key={resource.id}>
                    <span>
                      <strong>{resource.name}</strong>
                      <small>{resource.capabilities.join(" · ")}</small>
                    </span>
                    <input
                      type="checkbox"
                      checked={availableResourceIds.includes(resource.id)}
                      onChange={(event) =>
                        setResourceAvailable(resource.id, event.target.checked)
                      }
                      aria-label={`${resource.name} available`}
                      disabled={loading}
                    />
                  </label>
                ))}
              </div>
              <div className="control-block">
                <h3>Travel time</h3>
                {baseScenario?.resources.flatMap((resource) =>
                  resource.travel_times.map((route) => (
                    <label
                      className="travel-control"
                      key={`${resource.id}-${route.asset_id}`}
                    >
                      <span>
                        {resource.name}
                        <small>
                          to{" "}
                          {baseScenario.assets.find(
                            (asset) => asset.id === route.asset_id,
                          )?.name ?? route.asset_id}
                        </small>
                      </span>
                      <input
                        type="number"
                        min={0}
                        max={Math.max(
                          0,
                          (scenario?.horizon_minutes ?? 1) -
                            route.setup_minutes -
                            1,
                        )}
                        value={
                          resource.travel_times.find(
                            (item) => item.asset_id === route.asset_id,
                          )?.travel_minutes ?? route.travel_minutes
                        }
                        onChange={(event) =>
                          updateTravelTime(
                            resource.id,
                            route.asset_id,
                            Math.min(
                              Math.max(0, Number(event.target.value)),
                              Math.max(
                                0,
                                (scenario?.horizon_minutes ?? 1) -
                                  route.setup_minutes -
                                  1,
                              ),
                            ),
                          )
                        }
                        aria-label={`${resource.name} travel minutes to ${route.asset_id}`}
                        disabled={
                          loading || !availableResourceIds.includes(resource.id)
                        }
                      />
                      <small>min</small>
                    </label>
                  )),
                )}
              </div>
              <div className="control-block">
                <h3>Coverage trade-off</h3>
                <p>
                  Permit a lower total score when it improves the least-served
                  demand’s coverage.
                </p>
                <label htmlFor="fairness-tolerance">
                  Up to {(tolerancePpm / 10_000).toFixed(0)}% score reduction
                </label>
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
                <small>
                  This is a human-selected policy, not an ethical ranking.
                </small>
              </div>
            </div>
          </section>
        </details>
        <footer className="footer">
          <span>LIFELINE · Decision support prototype</span>
          <span>
            Synthetic inputs. Deterministic model. Not an operational
            recommendation.
          </span>
        </footer>
      </div>
      <dialog
        ref={reviewDialog}
        onCancel={() => setPendingChange(null)}
        onClose={() => setPendingChange(null)}
        aria-labelledby="review-title"
      >
        <div className="review-content">
          <h2 id="review-title">
            {pendingChange?.kind === "scenario"
              ? "Discard draft changes?"
              : "Review response changes"}
          </h2>
          <p>
            {pendingChange?.kind === "scenario"
              ? "Your current edits have not been evaluated. Confirm to discard them and load the selected scenario."
              : "Confirm these inputs to replace the current model result. This runs a simulation; it does not dispatch crews."}
          </p>
          <ul>
            {changedInputs.map((change) => (
              <li key={change}>{change}</li>
            ))}
          </ul>
          <div className="dialog-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                reviewDialog.current?.close();
                setPendingChange(null);
              }}
            >
              Keep editing
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={() => {
                const change = pendingChange;
                reviewDialog.current?.close();
                setPendingChange(null);
                if (change?.kind === "scenario") changeScenario(change.key);
                else if (scenario) void runEvaluation(scenario, tolerancePpm);
              }}
            >
              {pendingChange?.kind === "scenario"
                ? "Discard and load scenario"
                : "Confirm and recompute"}
            </button>
          </div>
        </div>
      </dialog>
    </main>
  );
}

export function relatedAssets(
  assets: Asset[],
  selectedId: string,
): Set<string> {
  if (!selectedId) return new Set();
  const upstream = new Map(
    assets.map((asset) => [
      asset.id,
      asset.dependency_groups.flatMap((group) => group.provider_asset_ids),
    ]),
  );
  const downstream = new Map<string, string[]>();
  for (const [target, providers] of upstream)
    for (const provider of providers)
      downstream.set(provider, [...(downstream.get(provider) ?? []), target]);
  const result = new Set([selectedId]);
  for (const graph of [upstream, downstream]) {
    const pending = [selectedId];
    const visited = new Set<string>();
    while (pending.length) {
      const id = pending.pop()!;
      if (visited.has(id)) continue;
      visited.add(id);
      result.add(id);
      pending.push(...(graph.get(id) ?? []));
    }
  }
  return result;
}

function assetStateLabel(state: TimeStep["assets"][number] | undefined) {
  if (!state) return "Awaiting simulation";
  if (state.physical_fault_active)
    return "Physical fault · backup cannot repair this asset";
  if (!state.service_available) return "Service unavailable at this minute";
  if (state.unsatisfied_dependency_group_ids.length)
    return `Service sustained by reserve · ${state.buffer_units} units remaining`;
  return "Service available at this minute";
}

function describeChanges(
  previous: Scenario | undefined,
  draft: Scenario | null,
  previousTolerance: number,
  tolerance: number,
): string[] {
  if (!previous || !draft) return [];
  const changes: string[] = [];
  for (const resource of previous.resources) {
    const updated = draft.resources.find((item) => item.id === resource.id);
    if (!updated) changes.push(`${resource.name}: available → unavailable`);
    else
      for (const route of resource.travel_times) {
        const next = updated.travel_times.find(
          (item) => item.asset_id === route.asset_id,
        );
        if (next && next.travel_minutes !== route.travel_minutes)
          changes.push(
            `${resource.name} to ${draft.assets.find((asset) => asset.id === route.asset_id)?.name ?? route.asset_id}: ${route.travel_minutes} → ${next.travel_minutes} min`,
          );
      }
  }
  for (const resource of draft.resources)
    if (!previous.resources.some((item) => item.id === resource.id))
      changes.push(`${resource.name}: unavailable → available`);
  if (previousTolerance !== tolerance)
    changes.push(
      `Permitted score reduction: ${previousTolerance / 10_000}% → ${tolerance / 10_000}%`,
    );
  return changes.length
    ? changes
    : ["Inputs restored to the previous run. Recompute to confirm the result."];
}

function humanAssetName(name: string) {
  return name
    .replace(/^(Failed|Interrupted|Finite) /, "")
    .replace("deep-sector ", "")
    .replace(/^./, (char) => char.toUpperCase());
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
    const asset = scenario.assets.find(
      (item) => item.id === action.target_asset_id,
    );
    const group = asset?.dependency_groups.find(
      (item) => item.id === action.dependency_group_id,
    );
    const resource = scenario.resources.find(
      (item) => item.id === action.resource_id,
    );
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
  const sharedTarget = [...complementaryAssignments.entries()].find(
    ([, assignments]) =>
      new Set(assignments.map((assignment) => assignment.groupId)).size > 1,
  );
  const sharedAsset = sharedTarget
    ? scenario.assets.find((asset) => asset.id === sharedTarget[0])
    : undefined;
  const comparisons = evaluation.optimization.baseline_comparisons.filter(
    (item) => item.baseline === "static_priority" || item.baseline === "greedy",
  );

  const improvedServices = [
    ...new Set(
      plan.demand_metrics
        .filter(
          (metric) =>
            comparisons.length > 0 &&
            comparisons.every((comparison) => {
              const baselineMetric = comparison.plan.demand_metrics.find(
                (item) => item.demand_id === metric.demand_id,
              );
              return (
                baselineMetric !== undefined &&
                metric.service_person_minutes >
                  baselineMetric.service_person_minutes
              );
            }),
        )
        .map((metric) => metric.service_type),
    ),
  ];
  const serviceImpact =
    improvedServices.length > 0
      ? ` Modeled service delivery for ${improvedServices.join(" and ")} is higher than in the ${comparisons.map((c) => (c.baseline === "static_priority" ? "static-priority" : "greedy")).join(" and ")} plans.`
      : "";

  const baselineServedServices = [
    ...new Set(
      comparisons.flatMap((c) =>
        c.plan.demand_metrics
          .filter((m) => m.service_person_minutes > 0)
          .map((m) => m.service_type),
      ),
    ),
  ];
  const planServedServices = [
    ...new Set(
      plan.demand_metrics
        .filter((m) => m.service_person_minutes > 0)
        .map((m) => m.service_type),
    ),
  ];

  let explanation: string;
  if (sharedAsset && sharedTarget) {
    if (
      baselineServedServices.length > 0 &&
      planServedServices.length > baselineServedServices.length
    ) {
      explanation = `A direct response protects ${baselineServedServices.join(" and ")}. Coordinating crews at ${sharedAsset.name} provides both missing inputs, protecting ${planServedServices.join(" and ")}.`;
    } else {
      explanation = `Coordinating separate crews at ${sharedAsset.name} provides both missing inputs.`;
    }
  } else {
    explanation =
      "The selected plan follows the declared service objective and fairness policy.";
  }

  return (
    <section className="recommendation-insight" aria-label="Why this plan">
      <p>
        {explanation}
        {serviceImpact}
      </p>
    </section>
  );
}

function DependencyMap({
  assets,
  initialStep,
  step,
  demands,
  selectedPlan,
  planLabel,
  loading,
  selectedAssetId,
  linkedAssets,
  onSelect,
  playing,
}: {
  assets: Asset[];
  initialStep: TimeStep | undefined;
  step: TimeStep;
  demands: Scenario["demands"];
  selectedPlan: Plan | undefined;
  planLabel: string;
  loading: boolean;
  selectedAssetId: string;
  linkedAssets: Set<string>;
  onSelect: (id: string) => void;
  playing: boolean;
}) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasWidth, setCanvasWidth] = useState(900);
  useLayoutEffect(() => {
    const element = canvasRef.current;
    if (!element) return;
    const measure = () => {
      const width = Math.round(element.getBoundingClientRect().width);
      if (width > 0) setCanvasWidth(width);
    };
    measure();
    const observer =
      typeof ResizeObserver === "undefined"
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
  const demandAssets = new Set(
    demands.map((demand) => demand.served_by_asset_id),
  );
  const edges = assets.flatMap((asset) =>
    asset.dependency_groups.flatMap((group) =>
      group.provider_asset_ids.map((providerId) => ({
        key: `${providerId}-${group.id}`,
        providerId,
        targetId: asset.id,
        service: group.service_type,
        alternatives: group.provider_asset_ids.length > 1,
      })),
    ),
  );
  const glyphX =
    layout.orientation === "vertical" ? -layout.nodeWidth / 2 + 40 : 0;
  return (
    <div
      ref={canvasRef}
      className={`network-canvas ${loading ? "network-loading" : ""}`}
      role="group"
      aria-label={`Infrastructure dependency graph for ${planLabel} at minute ${step.minute}`}
      data-orientation={layout.orientation}
    >
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="group"
        preserveAspectRatio="xMidYMin meet"
      >
        <defs>
          <marker
            id="arrow-tip"
            markerWidth="6"
            markerHeight="6"
            refX="5"
            refY="3"
            orient="auto"
          >
            <path d="M0,0 L6,3 L0,6 z" />
          </marker>
        </defs>
        <g className="edge-layer">
          {edges.map((edge, index) => {
            const from = layout.positions.get(edge.providerId),
              to = layout.positions.get(edge.targetId);
            if (!from || !to) return null;
            const state = states.get(edge.providerId);
            const status = !state
              ? "pending"
              : state.physical_fault_active
                ? "faulted"
                : !state.service_available
                  ? "failed"
                  : state.unsatisfied_dependency_group_ids.length
                    ? "buffered"
                    : "active";
            let path: string;
            let labelX = (from.x + to.x) / 2, labelY = (from.y + to.y) / 2;
            if (layout.orientation === "vertical") {
              const x = from.x + glyphX;
              const lane = 14 + (index % 3) * 8;
              labelX = 24 + (index % 3) * 8; labelY = (from.y + to.y) / 2;
              path = `M ${x - 25} ${from.y} C ${lane} ${from.y}, ${lane} ${to.y}, ${x - 25} ${to.y}`;
            } else {
              const x1 = from.x + 34,
                x2 = to.x - 34;
              if (to.level - from.level > 1) {
                const lane = 20 + index * 6;
                labelX = from.x + (to.x - from.x) * 0.3;
                labelY = from.y * 0.343 + to.y * 0.027 + lane * 0.63 - 12;
                path = `M ${from.x} ${from.y - 34} C ${from.x} ${lane}, ${to.x} ${lane}, ${to.x} ${to.y - 34}`;
              } else {
                const curve = Math.max(30, (x2 - x1) * 0.5);
                path = `M ${x1} ${from.y} C ${x1 + curve} ${from.y}, ${x2 - curve} ${to.y}, ${x2} ${to.y}`;
              }
            }
            const providerName = humanAssetName(assets.find((asset) => asset.id === edge.providerId)?.name ?? edge.providerId);
            const targetName = humanAssetName(assets.find((asset) => asset.id === edge.targetId)?.name ?? edge.targetId);
            const wasAvailable = initialStep?.assets.find((item) => item.asset_id === edge.providerId)?.service_available;
            const edgeLabel = `${edge.service} · ${status === "active" || status === "buffered" ? wasAvailable === false ? "restored" : "available" : status === "pending" ? "pending" : "unavailable"}`;
            const linked =
              selectedAssetId &&
              linkedAssets.has(edge.providerId) &&
              linkedAssets.has(edge.targetId);
            return (
              <g
                key={edge.key}
                className={`edge-group edge-${status} ${selectedAssetId && !linked ? "context-dimmed" : ""} ${linked ? "edge-linked" : ""}`}
              >
                <title>{`${providerName} → ${targetName}: ${edgeLabel}${edge.alternatives ? "; alternative provider (OR)" : "; required provider"}`}</title>
                <path d={path} markerEnd="url(#arrow-tip)" />
                {(layout.orientation === "horizontal" && (!selectedAssetId || linked)) && <text className="edge-label" x={labelX} y={labelY} textAnchor="middle">{edgeLabel}</text>}
                {playing && (status === "active" || status === "buffered") && (
                  <circle className="service-tracer" r="3">
                    <animateMotion
                      dur="1.8s"
                      repeatCount="indefinite"
                      path={path}
                    />
                  </circle>
                )}
              </g>
            );
          })}
        </g>
        <g className="node-layer">
          {assets.map((asset) => {
            const position = layout.positions.get(asset.id);
            if (!position) return null;
            const state = states.get(asset.id);
            const backup = selectedPlan?.interventions.some(
              (action) =>
                action.target_asset_id === asset.id &&
                step.active_intervention_ids.includes(action.id),
            );
            const status = !state
              ? "pending"
              : state.physical_fault_active
                ? "faulted"
                : !state.service_available
                  ? "offline"
                  : backup
                    ? "backup"
                    : state.unsatisfied_dependency_group_ids.length
                      ? "buffered"
                      : "online";
            const restored = state?.service_available && initialStep?.assets.find((item) => item.asset_id === asset.id)?.service_available === false;
            const statusLabel = {
              pending: "Awaiting simulation",
              faulted: "Physical failure",
              offline: "Service unavailable",
              backup: restored ? "Restored with backup" : "Backup active",
              buffered: "On reserve",
              online: restored ? "Service restored" : "Service available",
            }[status];
            const mobile = layout.orientation === "vertical";
            const name = humanAssetName(asset.name);
            const lines = wrapAssetName(
              name,
              mobile
                ? Math.max(14, Math.floor((layout.width - 128) / 8))
                : Math.max(19, Math.floor(layout.nodeWidth / 7.5)),
            );
            const icon =
              asset.buffer.capacity_units > 0 && asset.provides === "power"
                ? "battery"
                : asset.provides === "water"
                  ? "drop"
                  : asset.provides === "power"
                    ? "bolt"
                    : asset.provides === "medical"
                      ? "medical"
                      : asset.provides === "air"
                        ? "air"
                        : "branch";
            return (
              <g
                key={asset.id}
                transform={`translate(${position.x},${position.y})`}
                className={`asset-node node-${status} ${demandAssets.has(asset.id) ? "node-demand" : ""} ${selectedAssetId === asset.id ? "node-selected" : ""} ${selectedAssetId && !linkedAssets.has(asset.id) ? "context-dimmed" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`${asset.name}: ${statusLabel}`}
                aria-pressed={selectedAssetId === asset.id}
                onClick={() => onSelect(asset.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(asset.id);
                  }
                }}
              >
                <rect className="node-hit-area" x={-layout.nodeWidth / 2} y={-44} width={layout.nodeWidth} height={layout.nodeHeight} fill="transparent" aria-hidden="true" />
                <g className="node-marker" transform={`translate(${glyphX},0)`}>
                  <circle className="node-halo" r="42" />
                  <circle className="node-disc" r="31" />
                  <circle
                    className="state-ripple"
                    key={`${status}-${planLabel}`}
                    r="34"
                  />
                  <g transform="translate(-12,-12)" className="node-symbol">
                    <Icon name={icon} />
                  </g>
                  <g transform="translate(23,23)" className="node-status-badge">
                    <circle r="10" />
                    <text y="4" textAnchor="middle">
                      {status === "faulted" || status === "offline"
                        ? "!"
                        : status === "pending"
                          ? "…"
                          : status === "buffered"
                            ? "~"
                            : "✓"}
                    </text>
                  </g>
                </g>
                <text
                  className="node-name"
                  x={mobile ? glyphX + 60 : 0}
                  y={mobile ? -15 : 56}
                  textAnchor={mobile ? "start" : "middle"}
                >
                  {lines.map((line, index) => (
                    <tspan
                      key={index}
                      x={mobile ? glyphX + 60 : 0}
                      dy={index ? 19 : 0}
                    >
                      {line}
                    </tspan>
                  ))}
                </text>
                <text
                  className="node-status"
                  x={mobile ? glyphX + 60 : 0}
                  y={mobile ? lines.length * 19 + 1 : lines.length * 19 + 65}
                  textAnchor={mobile ? "start" : "middle"}
                >
                  {statusLabel}
                </text>
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
    const next = new Set(visiting).add(asset.id);
    const providers = asset.dependency_groups.flatMap((group) =>
      group.provider_asset_ids
        .map((id) => byId.get(id))
        .filter((item): item is Asset => Boolean(item)),
    );
    const level = providers.length
      ? Math.max(...providers.map((provider) => levelOf(provider, next))) + 1
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
  const positions = new Map<
    string,
    { x: number; y: number; level: number; row: number }
  >();
  if (width >= Math.max(700, (maxLevel + 1) * 190 + maxLevel * 24 + 28)) {
    const nodeWidth = Math.min(
      220,
      (width - 28 - maxLevel * 24) / (maxLevel + 1),
    );
    let maxRows = 1;
    for (const [level, items] of byLevel) {
      maxRows = Math.max(maxRows, items.length);
      items.forEach((asset, row) => {
        let y = 100 + row * 170;
        let x = maxLevel
          ? nodeWidth / 2 + 14 + (level * (width - nodeWidth - 28)) / maxLevel
          : width / 2;
        if (
          maxLevel === 2 &&
          level === 1 &&
          items.length === 2 &&
          items.filter((item) => item.dependency_groups.length > 1).length === 1
        ) {
          const complex = asset.dependency_groups.length > 1;
          y = complex ? 185 : 65;
          x += complex ? -24 : 45;
        }
        if (maxLevel === 2 && level === 2 && items.length === 2)
          y = 100 + row * 170;
        positions.set(asset.id, { x, y, level, row });
      });
    }
    return {
      orientation: "horizontal" as const,
      width,
      height: Math.max(390, 220 + (maxRows - 1) * 170),
      nodeWidth,
      nodeHeight: 140,
      positions,
    };
  }
  const nodeWidth = Math.max(160, width - 32);
  const ordered = [...assets].sort(
    (a, b) => (levels.get(a.id) ?? 0) - (levels.get(b.id) ?? 0),
  );
  ordered.forEach((asset, row) =>
    positions.set(asset.id, {
      x: width / 2,
      y: 70 + row * 144,
      level: levels.get(asset.id) ?? 0,
      row,
    }),
  );
  return {
    orientation: "vertical" as const,
    width,
    height: ordered.length * 144 + 20,
    nodeWidth,
    nodeHeight: 140,
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
  const exhaustiveSearch =
    evaluation?.receipt.payload.search.exhaustive_search_complete ?? false;

  return (
    <section
      className={`receipt-panel ${className}`}
      id="decision-audit"
      aria-labelledby="audit-title"
    >
      <div className="receipt-heading">
        <div>
          <span className="context-label">Decision audit</span>
          <h2 id="audit-title">A recommendation you can check</h2>
          <p>
            Decision Receipt · Reconstruct the inputs, replay the result and
            check the alternatives.
          </p>
        </div>
        <Icon name="shield" />
      </div>
      <div className="audit-grid">
        <div className="audit-explanation">
          <p>
            The verifier derives outcomes from the replay and independently
            enumerates the supported plans. It does not call the optimizer.
          </p>
          <p>
            Both paths use the same versioned simulator. A pass confirms model
            consistency, not physical accuracy, operational safety or
            authorship.
          </p>
          <div className="receipt-summary">
            <span>Search</span>
            <strong>
              {evaluation
                ? `${formatNumber(evaluation.receipt.payload.search.plans_evaluated)} plans · ${exhaustiveSearch ? "exhaustive" : "bound reached"}`
                : "Awaiting evaluation"}
            </strong>
          </div>
          <p className="audit-scenario">For {scenarioName}</p>
          <button
            className="primary-button"
            type="button"
            onClick={() => evaluation && onVerify(evaluation.receipt)}
            disabled={!evaluation || verifying || stale}
          >
            {verifying ? "Verifying receipt…" : "Verify this decision"}
            <Icon name="arrow" />
          </button>
          <p className="receipt-gate" role="status">
            {stale
              ? "Recompute before verifying this receipt."
              : verifying
                ? "Backend replay and verification are running. Checks appear when completed."
                : verification?.valid
                  ? "Receipt verified"
                  : "Verification runs on the Python backend."}
          </p>
        </div>
        <div
          className="verification-result"
          aria-live="polite"
          aria-busy={verifying}
        >
          <h3>
            {verification
              ? verification.valid
                ? "All seven checks passed"
                : "Verification found issues"
              : "Seven checks. One replayable record."}
          </h3>
          <ul className="verification-checks">
            {CHECKS.map(([key, label]) => {
              const status = verification?.[key] ?? "not_checked";
              return (
                <li key={key}>
                  <span className={`check-dot check-${status}`} />
                  {label}
                  <strong>
                    {verifying
                      ? "checking"
                      : status === "not_checked"
                        ? "not checked"
                        : status.replaceAll("_", " ")}
                  </strong>
                </li>
              );
            })}
          </ul>
          {verification?.issues.length ? (
            <ul className="verification-issues">
              {verification.issues.map((issue, index) => (
                <li key={`${issue.code}-${index}`}>
                  <strong>{issue.code}</strong> {issue.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      <div className="audit-details">
        <details className="receipt-details">
          <summary>Inspect receipt payload and digest</summary>
          <code className="digest-label">
            {evaluation?.receipt.integrity.digest ??
              "Receipt not yet available"}
          </code>
          <pre>
            {evaluation
              ? JSON.stringify(evaluation.receipt, null, 2)
              : "Evaluate a scenario first."}
          </pre>
        </details>
        <details>
          <summary>Model assumptions and limitations</summary>
          <div className="assumptions">
            <ul>
              {evaluation?.receipt.payload.assumptions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <ul>
              {evaluation?.receipt.payload.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </details>
      </div>
    </section>
  );
}

function Icon({ name }: { name: string }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
  switch (name) {
    case "battery":
      return (
        <svg {...common}>
          <rect x="3" y="6" width="16" height="12" rx="3" />
          <path d="M21 10v4M7 10v4M11 10v4" />
        </svg>
      );
    case "medical":
      return (
        <svg {...common}>
          <path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z" />
        </svg>
      );
    case "bolt":
      return (
        <svg {...common}>
          <path d="m13 2-3 9h7l-6 11 2-9H6z" />
        </svg>
      );
    case "check":
      return (
        <svg {...common}>
          <path d="m5 12 4 4L19 6" />
        </svg>
      );
    case "arrow":
      return (
        <svg {...common}>
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      );
    case "branch":
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="2" />
          <circle cx="18" cy="18" r="2" />
          <path d="M8 6h2a4 4 0 0 1 4 4v4a4 4 0 0 0 4 4" />
        </svg>
      );
    case "refresh":
      return (
        <svg {...common}>
          <path d="M20 7v5h-5M4 17v-5h5" />
          <path d="M5.5 9a7 7 0 0 1 11.6-2.6L20 12M4 12l2.9 5.6A7 7 0 0 0 18.5 15" />
        </svg>
      );
    case "play":
      return (
        <svg {...common} fill="currentColor" stroke="none">
          <path d="m8 5 11 7-11 7z" />
        </svg>
      );
    case "pause":
      return (
        <svg {...common} fill="currentColor" stroke="none">
          <path d="M7 5h4v14H7zM14 5h4v14h-4z" />
        </svg>
      );
    case "drop":
      return (
        <svg {...common}>
          <path d="M12 3s6 6.4 6 11a6 6 0 0 1-12 0c0-4.6 6-11 6-11Z" />
          <path d="M9 15a3 3 0 0 0 3 3" />
        </svg>
      );
    case "air":
      return (
        <svg {...common}>
          <path d="M3 8h12a3 3 0 1 0-3-3M2 12h17a3 3 0 1 1-3 3M5 16h7a2 2 0 1 1-2 2" />
        </svg>
      );
    case "shield":
      return (
        <svg {...common}>
          <path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      );
    case "warning":
      return (
        <svg {...common}>
          <path d="M12 3 2.8 19h18.4L12 3Z" />
          <path d="M12 9v4m0 3h.01" />
        </svg>
      );
    default:
      return null;
  }
}

export default App;
