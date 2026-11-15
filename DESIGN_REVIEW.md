# Light-first LIFELINE redesign

This direction supersedes the rejected graphite workspace. It uses a consumer-style light canvas, spacious service markers and one dominant recommended-response sheet. The inspiration is map interaction and progressive disclosure, not geographic accuracy: the UI explicitly calls the network a schematic. No roads, locations, flows or outcomes are invented.

## First-view hierarchy

At 1440 × 900 the incident heading and context identify the failed supplies and affected communities. A horizontal briefing shows the recommended target, needed inputs, measured benefit and primary Watch recovery action. Beneath it, a full-width network workspace puts replay transport above the visualization. The coupled scenario shows a **53% higher priority-weighted service score**, with exact scores **1,100 versus 720** and the full unit retained. This percentage is not an increase in unweighted service delivery or lives saved.

Assignment details, baseline explanations, whole-horizon coverage and technical evidence are disclosures. A visible decision-audit link leads to the seven-check verifier. On phones the recommendation precedes the vertically arranged network. Label wrapping uses available width; primary graph labels are 17px (16px on phones). Status words and !/✓/~ badges supplement color.

## Actual resource evaluation

- **TasteSkill:** rechecked the supplied repository/skill URL; live/raw access still returns 404. The previously accessible cached audit sequence (scan, diagnose, validate in the browser) informs the review. No full local skill installation or new source access is claimed.
- **tweakcn:** reviewed its official paired-token schema again. Applied light surface/foreground, focus, semantic status, radius and spacing roles in plain CSS. The actual UI typeface is now the system sans stack, with monospace confined to receipt payloads. Removed unused Google Fonts requests. No shadcn dependency.
- **21st.dev:** rechecked its component catalog and retained the relevant disclosure and visible-choice patterns. Baselines are a selectable, on-demand comparison list rather than four competing cards. Native controls preserve keyboard semantics; no third-party component source was copied or package installed.
- **Magic UI:** reviewed Animated Beam and Blur Fade references again. Adapted endpoint-anchored path motion and short surface/disclosure transitions using native SVG/CSS. Replay tracers appear only for available providers while replay is running; they indicate model availability, not physical flows. Reduced-motion preferences disable CSS motion, smooth scrolling and visible SVG tracers.
- **Figma:** confirmed the connection again, but a read request was blocked by the Starter-plan MCP quota. No new Figma design or visual review is claimed for this direction. Actual application screenshots drove desktop/mobile review.

## Visualization and motion

Infrastructure is represented by service icons in large circular markers, with readable names and explicit status text. A structural layout heuristic separates multi-input hubs from reserve providers where the graph supports it. Long bypass dependencies use an outer lane. Selecting an asset emphasizes connected paths and immediately names its required inputs/providers in the map heading; the detailed inspector remains available below.

Motion families include surface entrances, anchored selection halos, state-change rings, availability tracers during replay, responsive node transitions, hover/press feedback, comparison bar reveals, contextual drawers, confirmation-dialog entrance and verifier status marks. Motion never delays computation, increments invented work counts or changes model state. All outcomes still come from backend traces.

## Preserved interactions and limits

Draft edits remain separate from the evaluated scenario. Confirmation, cancellation, scenario-change confirmation, stale-result gating, retry confirmation, baseline switching, replay completion and independent receipt verification are preserved. All five built-in scenarios were exercised through the running frontend and actual backend. The simulator, optimizer, verifier, API contracts, security limits, hosting configuration and package dependencies are unchanged.

Browser review covered the 1440px desktop acceptance view, a 390px mobile first view, and the mobile map. It found no horizontal overflow and confirmed readable labels. Review caused three concrete fixes: assignment details were collapsed to reduce mobile density, the benefit headline was corrected to describe a weighted score, and narrow-screen label wrapping was based on actual available width. The main scenario still produces 1,100 versus 720, and its original receipt passes all seven checks.

Remaining constraints: phone maps require vertical scrolling; complex arbitrary networks can still contain crossing connections; the layout is schematic, not GIS; no unfamiliar-user study or formal accessibility audit is claimed. Passing tests supplement rather than replace visual review. Public rollout must be verified independently of GitHub CI.

## Recovery clarity pass — November 15

Reviewed the deployed screen before editing, then inspected Watermelon UI’s home and animated-component catalog and Cult UI’s Dynamic Island, Floating Panel and Direction Aware Tabs documentation. Selected the compact transport/toolbar and anchored disclosure principles, implemented in existing React/CSS; no external component code or package was installed. A phone-shaped notification or decorative dashboard template would not explain this simulation, so neither was copied.

The former map-and-side-sheet composition is now a single horizontal response briefing followed by a full-width recovery workspace. Watch recovery selects the recommended trace, starts from minute zero and takes the user to the map. Persistent desktop transport, keyboard-operable scrubber and initial/end-boundary buttons distinguish the selected instant from whole-horizon benefit. Phone layout puts Watch recovery before the score explanation. Comparison, coverage, assignment details and receipt verification remain available.

Supply paths carry service names and availability on desktop, with dashed/solid styles as well as color. A restored label is derived by comparing the current backend state with the selected trace’s initial state. Physical faults remain faults when temporary downstream backup restores service. Selection explains AND across input groups, OR within providers and current provider supply status. Mobile review found SVG groups had unpainted gaps that could miss taps; transparent rectangular hit areas now cover each complete marker/label target.

The horizon endpoint is shown accurately. In the coupled scenario, air and water are available during minutes 1–5, then temporary interventions end at minute 6. The endpoint contributes no service time; the 1,100 score covers intervals starting at minutes 0–5. The UI labels the end boundary and explains expired backup rather than fabricating sustained recovery. Score copy defines population × served minutes × priority weight.
