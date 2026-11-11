# Skill/tool audit vs Codex CLI (2026-11-11)

Question (idea: ai-workbench skill audit): how does our agent tooling compare
against commercial agents, especially Codex? Sources: local inventory
(packages/ai_agent tools + skills + dashboard executor) and the Codex CLI
Features doc + two independent mirrors of its tool architecture (bodies
inspected, not snippets).

## Our inventory (verified)

Tools: read/create/edit/list/find/grep, git status/diff, shell, python
runtime/navigate, rename preview/apply, staged-file, delegate_task,
owner-task/ask-owner, plus search_web/fetch_url/research_report — the
research trio exists but is wired into NEITHER the coding registry nor the
dashboard executor. Skills: 5 fixed allowlisted sources; provider-native CLI
does not discover them as skills.

## Ranked gaps (Codex → us)

1. **MCP extensibility** (high): Codex auto-launches MCP servers; we have a
   fixed registry, no MCP client/server.
2. **Web search on by default** (high, cheap fix): ours exists but unwired.
3. **Image inputs** (med): absent; read_file is text-only.
4. **Session resume** (med): drain receipts only; every run starts fresh.
5. **Atomic multi-file patch** (med): per-file edits only, no transaction.
6. **Plan tool** (med): absent; only prompt guidance.
7. **AGENTS.md auto-load** (med): executor uses a fixed system prompt.
8. **Approval modes** (med): coarse presets vs per-step inline approval.
9. **Custom slash commands** (low-med): fixed allowlist vs user-authored.
10. **Parallel tool calls** (low-med): unverified, likely serial.
11. **Review presets** (low): staged/unstaged only.
12. **Cloud best-of-N** (low): one-level delegation only.

Near-parity: sandbox design (ours defaults off), multi-agent roles.

## Our leads over Codex

Staged-write review flow (executor cannot direct-write); fail-closed
owner-task inbox; two-phase rename + AST navigation; skill prerequisite
contracts; cost/privacy routing with outcome demotions; groundedness gate +
compaction guards; pinned-HTTP research fetch (once wired).

## Recommended next (brief already queued)

Wire web_search first (small, safe); queue MCP/plan/patch designs.
