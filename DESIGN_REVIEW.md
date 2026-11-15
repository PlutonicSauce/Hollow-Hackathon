# LIFELINE launch redesign

This milestone replaces the Field Dossier dashboard with a graphite infrastructure workspace. The interface answers: what failed, what depends on it, what changes under each response, and how can that result be checked? Backend algorithms, receipt format, public limits, and hosting architecture are unchanged.

## Audit and decision

The previous live screen changed the scenario title into a long fault statement, put the graph beside a dense recommendation, pushed comparison scores below the first viewport, and buried verification beneath controls. Monospace labels, uppercase captions, repeated explanations, and many small borders weakened the hierarchy. Draft travel edits also changed displayed arrival labels before a new result existed.

The new hierarchy is incident context → live infrastructure workbench → recommended assignments and full-simulation coverage → decision audit → disclosed draft controls. Explore, Response, and Decision audit navigation link those parts. Four visible plan choices control the map, per-minute community status, events, and aggregate coverage. The map uses one faint blueprint grid; there is no film grain, speckle, contour overlay, or decorative animation.

## Resource evaluation and actual use

| Resource | Inspection and selected technique | Applied to LIFELINE |
| --- | --- | --- |
| [TasteSkill](https://github.com/tasteskill/tasteskill/blob/main/skills/redesign-skill/SKILL.md) | The supplied repository and raw skill fetches returned 404; a cached GitHub rendering exposed its existing-project audit sequence: scan the stack, diagnose generic patterns, then improve the existing implementation without breaking behavior. This was a partial source review, not a successful installation or full local skill invocation. | Inspected the live interface and source before implementation, identified hierarchy/state defects, retained React/vanilla CSS and backend behavior, and verified the new screen against real data. No TasteSkill package was installed. |
| [tweakcn](https://tweakcn.com), [official token schema](https://github.com/jnsahaj/tweakcn/blob/main/types/theme.ts) | The website shell was accessible but did not expose readable text to the web reader. Its official source defines paired surface/foreground roles, focus colors, typography, radius and spacing. | Semantic CSS variables unify graphite surfaces, legible foregrounds, sage selection, fault/reserve colors, focus rings, radius and timing. IBM Plex Sans remains the UI face; monospace is reserved for receipt evidence. No shadcn dependency. |
| [21st.dev](https://21st.dev/community/components) | Inspected the React component catalog, tabs/segmented-control listings, and a public navbar usage example. Full component source was account-gated. | Adapted visible single-choice controls and compact section navigation using native radio inputs and links. No third-party component code copied; no account or package added. Plan selection is discoverable and keyboard-operable. |
| [Magic UI](https://magicui.design/docs/components/animated-beam), [Blur Fade](https://magicui.design/docs/components/blur-fade) | Inspected endpoint-anchored SVG relationships and configurable short motion. Looping beams, blur entrances, tickers and decorative effects were rejected. | Existing SVG edges remain attached to their actual assets; short color/opacity transitions connect selection and backend state changes. Comparison bars grow from their left origin. Reduced-motion preferences disable transitions and smooth scrolling. No Motion dependency or fabricated progress. |
| [Figma exploration](https://www.figma.com/design/te2otFZ0QckmUbCaVz1If6) | Connected successfully, inspected available libraries, and created one editable primary-screen hierarchy exploration using IBM Plex Sans and a Simple Design System action instance. Apple libraries were not used because their EULA had not been accepted. | Used the incident/response/evidence exploration to structure the implementation; the clarified map-first requirement moved the live workbench ahead of the response summary. The Starter-plan tool quota blocked screenshot review, so no Figma visual sign-off is claimed. Final visual review used the running application. |
| Codex skill-creator | Available at the supplied system-skill path; reviewed the user-provided skill instructions. A reusable skill was considered. | No new skill created for a single redesign. This small decision record preserves the product-specific decisions without adding a redundant tool workflow. |

## Interaction and truthfulness

- SVG assets are focusable toggle buttons. Selection links ancestors and downstream assets, community coverage and timeline events; unrelated siblings are excluded. The inspector distinguishes a structural dependency from an actual outage.
- Per-minute availability comes from the selected backend trace. Percentage coverage and scores summarize the entire horizon and are labeled separately. Playback stops at the final boundary; replay can then be restarted explicitly.
- Displayed assignments, routes and event arrival times use the evaluated scenario, not draft edits. The previous result remains visible during recomputation, with verification gated until fresh inputs succeed.
- Important edits require a native modal showing the exact changes. Cancel preserves the draft. Confirm sends the changed scenario to the existing backend. Switching scenarios with unapplied edits also requires confirmation.
- Loading text reports actual request stages without invented percentages or delays. Finished runs expose actual plan counts and measured backend search time. Computation failures retain the previous result and offer retry.
- The audit shows all seven checks in a reserved result region. Digest, payload and model assumptions are progressive disclosures. Verification is independent of the optimizer, but shares the simulator; the UI says so.

## Verification and remaining limits

Frontend tests cover edited-input gating, confirmation/cancellation, baseline switching, invalid verification, failed recomputation, keyboard focus, asset selection, linked traversal, pending-run route consistency, replay completion, and graph bounds at 360/900/1400 pixels. Real-browser checks cover linked selection, keyboard replay, arrival-boundary service recovery, native confirmation, real recomputation and receipt verification. Phone/tablet checks at 390 and 768 pixels found no horizontal overflow. Production HTTP smoke tests check the real API, assets, known 1,100-versus-720 scores, receipt digest and serving limits.

The mobile map deliberately stacks assets and requires scrolling. The product still uses an abstract binary infrastructure model and synthetic scenarios. No streaming optimizer progress or physical flow visualization is implied. Future research with unfamiliar users would be useful; it was not fabricated for this milestone.
