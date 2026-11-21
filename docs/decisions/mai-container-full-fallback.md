# Mai container inference must preserve full fallback

Status: requirement accepted; execution placement awaiting owner decision.
Source: inbox `3dcbb514b324474ea61a054bafb4d387`, owner answer 2026-11-21.

The owner requires the whole qualifying fallback tree: restricting Mai to
Ollama or one model defeats its purpose. This rejects a single-model production
path. It does not waive privacy, billing, capability, approval or deadline
qualification, authorize paid inference, or reopen the accepted network-none
mailbox transport R.

Current implementation is insufficient: `relay_mailbox.RelayGrant` fixes one
model, `proxy_model_callback.ScopedGrant` enforces it, and the worker protocol
only carries role/content messages. Mai's `_execute_fallback_route` can switch
between native tool loops and external agent processes; it is not just another
text completion. No container Mai integration is established by the relay probe.

Remaining decision: where routing and execution live across the boundary.

| Option | Benefits | Costs and risks |
| --- | --- | --- |
| Host Mai orchestration with worker tool execution | Reuses existing full fallback and host credentials/CLI clients; preserves network-none worker. | Requires a narrow host-to-worker tool protocol and changes the original Mai-in-container placement; every tool and external CLI execution path must be contained. |
| Worker Mai orchestration with host execution mediation | Keeps routing in container Mai and network-none isolation. | Requires provider-neutral structured request/response, continuation and tool history transport, plus an external CLI execution bridge; substantially larger protocol and validation surface. |

Technical recommendation: host orchestration with worker tool execution,
because existing fallback already owns native and external execution. This is
a recommendation, not an accepted placement decision. External clients must
not regain unrestricted host shell/write authority through that placement.

Private context inspected in the main checkout: `os-isolation-integration.md`
(relevant, explicitly incomplete and partly truncated),
`mai-dashboard-wiring-plan.md` (dashboard entry-point context), and
`interactive-mai-plan.md` (older draft, not authority to change current approval
policy). ADR-095 remains the containment acceptance contract.

INCOMPLETE: obtain the execution-placement decision, implement the selected
bridge through drain and chat, then prove multi-provider/native/external
fallback, qualification exclusions, state/history continuity, shared budgets,
timeout/cancel cleanup and the ADR-095 negative containment matrix. Existing
relay tests establish only the current protocol, not this future bridge.
