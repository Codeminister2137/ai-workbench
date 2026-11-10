# Turn budgets: how vendors solve max-turns (research 2026-11-10)

Owner prompt: our runs keep dying at `max_action_rounds` (pilot 2026-11-10
died at 3 after list/read/grep). How do OpenAI, Meta, Anthropic solve it?

## Consensus: nobody governs by small fixed turn counts

**OpenAI Codex.** 1M-token window; native auto-compaction near the limit
plus explicit `/compact`. Newer models compact across windows (incl. an
opaque latent `compact` endpoint); internal runs exceed 24h. Key rule:
plan + success criteria live OUTSIDE the compacted context.

**Meta Muse (closest to our experience).** 1M window, model-managed
compaction, but the primary technique is structural: main agent +
parallel subagents for heavy work (cookbook: ~300 calls, context peaked
54%, never compacted), a `STATE.md` running state, goal conditioning,
async/parallel tools. Subagents carry the bulk; the main thread stays
lean. Isolated git worktrees per child; append-only event log.

**Anthropic Claude Code.** Auto-compact ~95% + `/compact [instructions]`
+ Pre/PostCompact hooks. Sliding window (last N verbatim, rest
summarized). Documented guidance: compact at task boundaries, never
mid-task; what must survive lives in files (CLAUDE.md/AGENTS.md),
not the conversation; summarize at tool-call boundaries and handoffs.

Common shape: **context-%-triggered compaction + delegation +
external durable state**. Fixed iteration caps exist only as backstops.

## Where we stand (gaps)

1. No loop compaction: our admission gate REFUSES on overflow instead
   of summarizing forward (rolling summaries exist only for chat).
2. Default action rounds = 3 — an order of magnitude below real tasks.
   (`loop.py`/`delegation_runner` default 10; messenger 4.)
3. Delegation exists (`DelegateTaskTool`) but CLI runs show
   `delegation: disabled`.
4. Good bones: decisions, handoff, inbox, run DB already live outside
   the loop — matches vendor guidance. Keep it that way.

## Recommendation (phased)

- Phase 0 (SHIPPED 2026-11-10, owner-approved): `--max-action-rounds`
  default 3→25, AgentLoop 10→50, messenger 4→25, plus partial+resume.
- Phase 1 (SHIPPED 2026-11-10, owner-approved): loop compaction at a
  char-budget threshold (`--loop-context-budget-chars`, default 100k) —
  summarize-then-continue with immune system instructions, rolling
  summaries, verbatim tail, and an anti-thrash cap.
- Phase 2 (SHIPPED 2026-11-10, owner-approved): delegation was already
  registered but unusable (validation rejected the model's `default`
  profile); fixed with a `default`=inherit alias plus system-prompt
  guidance. Proven live with a real child run.
- Standing rule: durable state (decisions, handoff, inbox) stays in
  files/DB, never only in the loop transcript.

Sources: OpenAI/Codex compaction coverage (Nov 2025–Oct 2026),
dev.meta.ai multi-turn-context-management cookbook, Meta Muse
announcements, Claude Code best-practices + harness guides (2026).
Fetched 2026-11-10; vendor docs move fast, recheck before building.
