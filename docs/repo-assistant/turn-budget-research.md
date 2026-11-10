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

- Phase 0 (now, no architecture): raise the effective round budget for
  real tasks via explicit `--max-action-rounds 8` per run. Do NOT raise
  the shipped default without owner approval (more flailing spend).
- Phase 1 (the real fix): loop compaction at a context-% threshold —
  summarize-then-continue preserving decisions/file states, steerable
  instructions, summary persisted to the run record. Needs owner
  approval as a slice (new behavior + spend profile).
- Phase 2: wire subagent delegation into CLI runs for heavy subtasks
  (main thread stays lean, Meta-style). Needs owner approval.
- Standing rule: durable state (decisions, handoff, inbox) stays in
  files/DB, never only in the loop transcript.

Sources: OpenAI/Codex compaction coverage (Nov 2025–Oct 2026),
dev.meta.ai multi-turn-context-management cookbook, Meta Muse
announcements, Claude Code best-practices + harness guides (2026).
Fetched 2026-11-10; vendor docs move fast, recheck before building.
