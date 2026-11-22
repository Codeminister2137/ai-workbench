# Allowance-aware routing and route refusals

Owner request 2026-11-22: avoid repeatedly selecting a nearly exhausted Codex
subscription while another qualifying allowance has substantial headroom; walk
past route-specific refusals without changing billing tiers or spend policy.

## Ranking

`recommend_model` and `prepare_execution` accept optional `allowance_remaining`
(route ID to remaining percent). Hard route overrides, privacy, capability,
quality, latency and spend admission run first. Then healthy/unknown routes
precede thin routes (<=20% remaining), which precede critical routes (<=5%).
Within a band the existing quality/latency/locality/cost score is unchanged.
`fallback_candidates` applies the same bands to both ordinary and explicit
caller/council priority ordering. Priority remains stable within each band.
This is a soft demotion, not a quota reservation or an admission bypass. Unknown
telemetry remains neutral so a reader failure cannot disable every route.
The trade-off is that unknown routes can precede measured thin routes, and a
healthy sufficient-quality route can precede a thin higher-grade route.

The provider-side `read_route_allowances` composes existing native readers and
normalization, reading each supported subscription once per ranking decision.
Only hard-admitted candidates are observed; forced single-route selections skip
ranking reads. The limiting remaining percentage across active windows wins;
expired windows and missing/invalid measurements do not invent fresh allowance.
Reader failures are neutral, cancellation propagates, and deadlines bound each
read. Observations stay transient; no quota registry or persistent format is added.
Native readers may contact account services; no task prompt is passed to them.

## Execution and scope

The repo coding CLI initial selection and dashboard automatic run selection wire
live snapshots into recommendation. The coding execution helper carries the same
snapshot so its second preparation does not silently revert the selected route.
A `FallbackSession` with `observe_allowance` refreshes eligible alternatives on
route failure, reusing the selected observation for its immediate diagnostics.
Sessions without an observer and pure recommender callers retain deterministic
catalog behavior unless they explicitly pass a snapshot. Readiness/query-only
surfaces are not all converted to live account probing.

Known pre-response HTTP 400 refusals (`NON_RETRYABLE` plus structured HTTP status),
known tool/context reroute messages, and the native admission context-fit refusal
that states no model request was sent can continue on another eligible route.
They exclude that route for the session, not the entire billing bucket. The same
request is never retried on that route; partial observable history is preserved
through the existing continuation mechanism. Authentication, privacy refusals,
timeouts, arbitrary fatal/configuration errors and unknown effects still stop.
No generic fatal-error catch was added. Existing quality policy, compatibility,
readiness, deadline, exclusion and cost constraints still govern every switch.
The walk also now retains existing explicit cost exemptions consistently with
preflight; no new exemptions or spending permission are introduced.

Mai's own adapters and standalone fallback loop are outside this repository-side
change. Repo adapter changes do not alter them. The documented Mai mailbox host
composition can benefit only when it uses the updated `FallbackSession` and wires
`observe_allowance=read_execution_allowance`; direct Mai execution needs equivalent
Mai-side ranking/error classification and separate deployment/validation. This
change does not claim Mai rollout or a successful live Mai run.

## Evidence and limits

Deterministic regression tests cover limiting Codex windows, Kiro remaining
semantics, deduplication, expired windows, missing/bad telemetry, hard quality
rejection, priority demotion, HTTP 400/context-fit continuation and fatal-stop
protection. They demonstrate policy behavior, not model quality or live account
availability. No hosted acceptance or new inference grant is used by these tests.

Investigation searched `site:docs.ollama.com context length context window API`
and `site:platform.moonshot.ai 400 invalid request context length`. Official Ollama
[context documentation](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx)
confirms context configuration; searches did not establish the cause of the
owner's particular Kimi 400. No saved provider response for that incident was
supplied. The code-level cause of walk termination is established: the session
previously rejected fatal classes and configuration context-fit errors before
candidate selection. No claim is made about the Kimi service's underlying cause.
