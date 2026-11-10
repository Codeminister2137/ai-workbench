# Package overlap / modularity analysis (2026-11-10, read-only + 2 wins)

Method: `find-duplication.py` (≥15 lines, 1350 functions) + static
cross-package import survey. No restructuring implemented; the two wins
below are local and behavior-preserving.

## 1. Actual dependency graph (measured)

- ai_orchestrator imports NOTHING outside itself (neutral contracts +
  decisions; callers inject implementations). This is dependency inversion
  done right — and it contradicts AGENTS.md's diagram (Orchestrator ↓ Provider).
- ai_provider runtime-imports ai_orchestrator (17 modules) and ai_agent
  (7 modules): acceptance harness, coding sessions, foreground tools,
  research execution, usage meters, fallback. Hosted/agent machinery grew
  inside the provider package.
- ai_agent wires all three (expected for the app layer).

The documented direction exists nowhere in code; the real one runs opposite.
`test_package_layering.py` now pins this: orchestrator must stay clean,
agent may wire provider+orchestrator, and the 20 provider up-importing
modules form a ratchet (shrinking welcome, growth fails loudly).

## 2. Clone scan dispositions

- ollama_models list_local vs list_running (105 nodes): UNIFIED into
  `_list_models_from_endpoint`; public wrappers kept (signatures, docstrings,
  behavior unchanged; 15 existing tests green). Residual wrapper match is
  inherent API shape, accepted.
- chat_transcripts get_session/get_rolling_summary + list_messages vs
  orchestrated_runs list_stages: same-shape SQLite readers. Lead only —
  unifying needs a shared helper both stores accept; queued as follow-up.
- Tool `.definition` boilerplate pairs (owner_tasks/staged, search/shell):
  declarative data in a shared shape; a helper would obscure. Accepted as is.
- My new ask_owner/OwnerTaskTool definitions did not cluster — fine.

## 3. Options for the layering drift (owner decision)

- A: Accept + document. Provider = execution implementations + hosted
  machinery; fix the AGENTS.md diagram; keep the ratchet. Cost: ~1 doc edit.
- B: Split. Move agent-machinery modules out of ai_provider (to ai_agent
  or a new ai_host package). Cost: large refactor, high regression risk.
- C: Hygiene per touch. Break runtime up-imports into protocols/callbacks
  incrementally whenever a listed module is edited. Cost: slow, steady.

Recommendation: A now (one honest paragraph kills the doc/code lie), C as
standing practice, B never unless a concrete pain (cycle, publish split)
forces it. Filed as inbox decision for the record.

## 4. Follow-ups (backlog-seeded)

- Shared SQLite-list/get helper for the transcript/run stores (needs both
  stores' buy-in on one shape).
- Per-module C passes whenever a pinned up-importer is touched.
