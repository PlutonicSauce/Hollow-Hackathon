# Coordination evidence

The design branch imports `coordination-certificates.patch` supplied in the handoff archive. The archive contained reference screenshots but no frontend source or CLAUDE_HANDOFF.md. Its API file preimage matched the checkout exactly; no originating commit SHA was supplied. The explorer completes the missing frontend using the imported Python implementation.

`POST /api/evaluate` adds `coordination_certificate` and `coordination_verification` alongside the unchanged Decision Receipt. Every subset of the recommended action set is replayed through the simulator. The certificate records integer scores, demand served-minute totals and asset availability at boundaries 0 through H. Only intervals 0 through H−1 contribute to service time. Browser switches select these recorded outcomes; they do not simulate results.

For the coupled fixture: no actions, generator alone and tanker alone score 0; both score 1,100. The two-action interaction is f(AB) − f(A) − f(B) + f(empty), here 1,100. For larger action sets the reported interaction is the full-set Harsanyi dividend, not a classification of all lower-order interactions. Removing an action measures necessity relative to this response's score.

Sufficient subsets match each demand's full-response served-minute total. Listed subsets are inclusion-minimal within the recommended actions. They are not globally minimum plans, proof of full recovery, or proof of identical service timing. Availability series expose timing separately. The greedy witness uses canonical assignments and simulator scores.

## Checking and limits

Python callers can use `engine.certificates.verify_coordination_certificate(scenario, certificate)`. Evaluation also runs it before returning results. Ten checks cover schema, scenario/body binding, canonical action metadata, subset replay, interaction/share, necessity, demand sufficiency, joint sufficiency, greedy witness and claim scope. Builder and verifier share the simulator and claim formulas: this establishes replay consistency, not fully independent verification. SHA-256 detects inconsistent contents; it is not a signature or authentication mechanism. Decision Receipt's separate seven checks remain unchanged.

There is no new public certificate-submission endpoint. At most four actions and 16 subsets are permitted. Public generation and replay checking run inside the existing admitted worker: eight-second wall limit, six-second CPU limit and Linux 256 MiB address-space cap. Existing request, graph, candidate, work, concurrency and rate limits remain enforced. Responses over eight million bytes are rejected without partial evidence. Structurally admitted inputs are not guaranteed to fit runtime or output limits; long Unicode identifiers can trigger bounded rejection. Local macOS measurements do not establish Render memory usage or production latency.

The explorer disables old evidence while inputs are stale and exposes detailed boundary states and verification scope. No real-world safety or lives-saved claim follows from this synthetic model.

## Product workspace

The primary workspace uses one action subset and one minute selection for its infrastructure graph, service timelines and full-window score. Crew switches select certificate replays; greedy/static comparisons select their existing backend plan traces. Switching preserves the minute and stops playback. The recommendation remains labeled separately from an explored counterfactual. Availability is never simulated in the browser. Node selection exposes AND across input groups and OR among providers; reserve and backup effects remain simulator outputs. Mathematical evidence and all seven Decision Receipt checks are progressively disclosed. Certificate checks remain distinct from the receipt audit.
