# Common inspection and selected skills

`--shared-tools inspection` selects the same six project-owned Git/read/search
operations for provider-native execution, Codex, Copilot and Kiro. Antigravity is
excluded until scoped MCP access is verified. This profile cannot edit or run
commands; it sets the read-only approval preset. Existing coding defaults and
the older Codex-only delegation option remain separate.

```powershell
.\scripts\repo-assistant.ps1 "Review the change" --mode review --shared-tools inspection --execute
.\scripts\repo-assistant.ps1 "Review the change" --mode review --skill review-repo-change --execute
```

Select privacy, cost and route settings appropriate to the task; the examples use
the existing local-only defaults. Selecting a supported skill implies inspection
unless a common profile was explicitly selected. Sources are project `.agents/skills`
and `packages/ai_agent/skills`, or repeat `--skill-dir PATH` to use explicit sources.
Exactly one source must match each name. Current prerequisite contracts support
`review-repo-change`; unknown skills are refused rather than claiming dependencies
were checked. Skill selection passes complete instructions to every route. It is
not evidence that a client's separate native skill menu was invoked.

Required root and selected-path nested `AGENTS.md` instructions are loaded intact,
before optional snippets. Their independent limit defaults to 64,000 characters;
`--instruction-budget-chars` changes it. Optional context retains its own total and
per-file limits. An instruction overflow or unreadable instructions refuses before
route preparation. Character limits alone do not establish model token capacity.
Native repairs and delegated requests retain the loaded instructions.

Common MCP configuration is passed per run. Kiro needs a generated project-local
agent file; the adapter uses a unique name and removes its unchanged file afterward,
including on failure. Existing configuration and changed generated files are
preserved. No user-wide grants or skill installations are performed. The native
client may also expose its own tools under its restrictions; required common
tools are the shared contract, not a promise of identical complete client menus.

2026-10-04 acceptance: synthetic Codex quota failure continued through real Copilot,
preserving inspection and selected instructions and finding the planted regression.
Fixture content stayed unchanged; Copilot reported one premium request. Real Kiro
used the production mapping to read a marker and removed its generated configuration.
These checks do not establish shared mutation permissions or complete coding parity.
