# Mai container inference must preserve full fallback

Status: placement accepted; implementation and containment proof INCOMPLETE.
Source: inbox `3dcbb514b324474ea61a054bafb4d387`, owner answer 2026-11-21.
Placement source: inbox `bd270333090148f6a4547badd653fb43`, owner selected
"Host Mai orchestration with isolated worker tools" on 2026-11-21.
No additional owner rationale was supplied.

The owner requires the whole qualifying fallback tree: restricting Mai to
Ollama or one model defeats its purpose. This rejects a single-model production
path. It does not waive privacy, billing, capability, approval or deadline
qualification, authorize paid inference, or reopen the accepted network-none
mailbox transport R.

At the original decision brief, `relay_mailbox.RelayGrant` fixed one model,
`proxy_model_callback.ScopedGrant` enforced it, and the worker protocol carried
only role/content messages. P2 subsequently added structured inference and
host fallback selection, but not the selected tool bridge. Mai's `_execute_fallback_route` can switch
between native tool loops and external agent processes; it is not just another
text completion. No container Mai integration is established by the relay probe.

Accepted placement: Mai orchestration runs on the host; tool execution stays
inside the isolated worker. The alternatives considered were:

| Option | Benefits | Costs and risks |
| --- | --- | --- |
| Host Mai orchestration with worker tool execution | Reuses existing full fallback and host credentials/CLI clients; preserves network-none worker. | Requires a narrow host-to-worker tool protocol and changes the original Mai-in-container placement; every tool and external CLI execution path must be contained. |
| Worker Mai orchestration with host execution mediation | Keeps routing in container Mai and network-none isolation. | Requires provider-neutral structured request/response, continuation and tool history transport, plus an external CLI execution bridge; substantially larger protocol and validation surface. |

Technical recommendation accepted by the owner: host orchestration with worker tool execution,
because existing fallback already owns native and external execution. This is
the accepted placement decision. External clients must
not regain unrestricted host shell/write authority through that placement.

Private context inspected in the main checkout: `os-isolation-integration.md`
(relevant, explicitly incomplete and partly truncated),
`mai-dashboard-wiring-plan.md` (dashboard entry-point context), and
`interactive-mai-plan.md` (older draft, not authority to change current approval
policy). ADR-095 remains the containment acceptance contract.

INCOMPLETE: implement the selected host-orchestration/worker-tool
bridge through drain and chat, then prove multi-provider/native/external
fallback, qualification exclusions, state/history continuity, shared budgets,
timeout/cancel cleanup and the ADR-095 negative containment matrix. Existing
relay tests establish only the current protocol, not this future bridge.

## Placement implementation audit (run bf5b63d2e3ac)

The existing P2 composition is a different, narrower seam: `relay_inference.py`
keeps `FallbackSession` on the host, while `RelayChatClient` and `AgentLoop`
run in the worker. It does not move Mai orchestration to the host or provide
host-to-worker tool dispatch. Its synthetic proof cannot close this source.

`mai_run.build_mai_executor` still invokes host Mai using the existing subprocess
or in-process path. `ExternalExecutionSettings.build` maps `trusted_local` to
`danger-full-access`; a working directory or shared-tool profile is not an OS
boundary. Production enablement must not reuse that path as contained execution.

Implementation must route host Mai's tools into the worker, preserve the full
native/external fallback tree and session state, and contain external clients'
built-in tools as well as shared tools. Wire both drain and resumed chat through
that path, with shared admission/budgets and timeout/cancel cleanup. Prove these
contracts and the ADR-095 negative matrix before closing `bd270333` or its parent.
The accepted answer authorizes this work; it is not a request to choose placement
again. No narrower inference-only implementation is accepted as full fallback.
