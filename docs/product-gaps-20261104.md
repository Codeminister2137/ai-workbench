# AI-first-developer product-gap analysis — 2026-11-04 (status swept 2026-11-09)

> Status sweep 2026-11-09: G6 RESOLVED (ADR-082 centralized, filters
> landed), G7 RESOLVED (validator + adversarial secrets/PII + approve
> flow + UI button all shipped), G8 RESOLVED (spend ledger with
> reserve-before-dispatch + deny-by-default, grants docs, dashboard
> panel). G9 RESOLVED (Schedule wired to fleet probe). G10/G11
> BRIEFED (audience a96f576b, notify c801d2f6 — owner decides).
> G12 DONE (company-run.md + Help view). G4/G5 verified still open
> but not prioritized; G1–G3 unchecked — verify before citing;
> this doc is a point-in-time analysis.

Perspective: a developer who wants to RUN A COMPANY'S DEVELOPMENT through
ai-workbench (client intake → plan → approve → execute → verify → report →
repeat across projects). Ranked by how hard each gap blocks that job.

Sources: worktree root `AGENTS.md`, `README.md`, `docs/architecture.md`,
`docs/project-map.md`, `docs/installation.md`, `docs/repo-coding-assistant.md`,
`packages/` (`ai_provider`, `ai_orchestrator`, `ai_agent`), `apps/`
(`ai_council`, `job_search`, `workbench_dashboard`), plus plans read
READ-ONLY from the main checkout at
`C:\Users\Jakub\PycharmProjects\ai-workbench\docs\plans`
(`product-roadmap-20261031.md`, `p4-agent-ux-proposal.md`,
`p5-spend-policy-proposal.md`, `p6-dashboard-proposal.md`,
`p7-project-file-format-proposal.md`, `p8-templates-scouting.md`,
`company-backlog-20261102.md`, `company-offering-draft.md`,
`track-b-20261104.md`, `backlog.md`, `morning-20261104.md`).
Those plan files are gitignored and absent here; citations below marked
`[plans]` refer to the main checkout.

## Ranked gaps

### G1. No first-5-minutes path (onboarding)

- **User job blocked:** a new developer (or the owner on a fresh machine)
  goes from clone to first assisted task. Today that is a maze.
- **Evidence:** [README.md](README.md:123-131) demands a 5-gate
  check chain (`sync`, full tests, `ruff check`, `ruff format --check`,
  `pyright`) before anything else; [installation.md](docs/installation.md:72-78)
  is 324 lines of manual per-tool recipes with pinned versions; the
  [getting-started flow](docs/repo-assistant/getting-started.md:22-47) is
  4+ commands plus 4 manual verify commands; there is no `doctor` /
  preflight command (verified: no `doctor` entry in
  [ai_agent CLI](packages/ai_agent/src/ai_agent/cli.py) or
  [repo_assistant_args](packages/ai_agent/src/ai_agent/repo_assistant_args.py)).
  There is no single preflight that tells a newcomer which of these
  gates failed and how to fix it — each gate's error must be decoded
  separately. (Reviewer note 2026-11-04: an earlier draft cited a
  worktree-local `program not found` anecdote; struck as a checkout
  artifact, not a product defect.)
- **Bounded slice:** add `ai-assistant doctor` — offline probes for
  Python/uv/venv, Ollama reachability + installed models, native-client
  binaries, `.env`/catalog presence — printing one fix-it list.
  Files: `packages/ai_agent/src/ai_agent/doctor.py` (+ CLI wiring),
  `tests/test_doctor.py` (offline, fake probes). Estimate: 4–6h.
- **Owner decision first?** No — diagnostic only, no behavior change.

### G2. No wired plan → approve → execute → report loop (daily dev loop)

- **User job blocked:** the P1 contract — "collaborative planning, owner
  approves the plan, AI executes, final report presents decisions"
  `[plans:product-roadmap-20261031.md:20-25]`. The pieces exist
  disconnected: CLI `--mode plan/review/implement`, dashboard chat,
  run receipts, inbox — but nothing links one plan to its approval,
  its run, and its final report.
- **Evidence:** dashboard chat turns are explicitly single-shot with no
  tools ([dashboard_chat.py](apps/workbench_dashboard/dashboard_chat.py:114-162),
  `_execute` builds one completion; [README](apps/workbench_dashboard/README.md:26-28)
  "Turns cannot run tools yet"); runs are read-only views of files made
  elsewhere ([dashboard_web_app.py](apps/workbench_dashboard/dashboard_web_app.py:139-148));
  README status for full coding workflows is "Experimental"
  ([README.md](README.md:104)).
- **Bounded slice:** link the records: `plan_id` on run files, required
  `report` field on run close (reuse `_request_run_report` at
  [dashboard_web_app.py](apps/workbench_dashboard/dashboard_web_app.py:447-476)),
  plan page shows linked runs + approval state. Files:
  `apps/workbench_dashboard/dashboard_stores.py`,
  `dashboard_web_app.py`, `web/app.js`, `tests/test_stores.py`,
  `tests/test_web_app.py` additions. Estimate: 6–8h.
- **Owner decision first?** Partially — P4 open Q1/Q2 (one-shot vs
  per-phase plan approval; implicit vs explicit steering approval)
  `[plans:p4-agent-ux-proposal.md:101-107]` shape the approval UX.
  Record-linking itself needs no decision.

### G3. Running loops cannot be steered (daily dev loop)

- **User job blocked:** redirecting a running agent ("stop, use X
  instead", "just do steps 1–2") without killing the session — the
  Muse-in-PowerShell pattern the owner likes
  `[plans:p4-agent-ux-proposal.md:9-25]`.
- **Evidence:** dashboard chat cannot drive runs at all (G2 evidence);
  CLI-side `coding_chat_input` arbitrates terminal input only
  ([coding_chat_input.py](packages/ai_agent/src/ai_agent/coding_chat.py));
  P4 recommendations 1–7 (turn grouping, synthesis template, phase
  header, activity pulse, pause/resume, plan amendment) are all
  unimplemented `[plans:p4-agent-ux-proposal.md:73-86]`.
- **Bounded slice (UI-only first):** P4 recs 1–3 in the dashboard —
  turn-grouped transcript collapsed by default, `Did/Found/Next/Needs
  owner` synthesis shape in the supervisor prompt
  ([dashboard_chat.py](apps/workbench_dashboard/dashboard_chat.py:29-33)),
  persistent phase header + step checklist rendered from plan files.
  Files: `apps/workbench_dashboard/web/app.js`, `web/app.css`,
  `dashboard_chat.py`, `tests/test_dashboard_ui.py`. Estimate: 6–10h.
- **Owner decision first?** Yes for the later half — pause/resume and
  plan-amendment semantics need P4 Q1/Q2/Q4 answers; the UI-only
  recs 1–3 need none.

### G4. No run timeline, cost ticker, or usage surfacing (visibility)

- **User job blocked:** glancing at Workbench and knowing what is
  happening, how far along, and what it costs — without reading raw logs.
- **Evidence:** dashboard `/api/status` returns counts only
  ([dashboard_web_app.py](apps/workbench_dashboard/dashboard_web_app.py:208-235));
  evidence view merges probe/eval snapshots only
  ([dashboard_web_app.py](apps/workbench_dashboard/dashboard_web_app.py:62-75));
  usage machinery (`turn_usage.py`, `account_usage.py`,
  `native_account_usage.py` in `ai_provider`) has no dashboard surface;
  P4 signal taxonomy (phase, checklist, pulse, ticker, badge, report
  card) `[plans:p4-agent-ux-proposal.md:27-40]` does not exist.
- **Bounded slice:** run-detail timeline from existing stage receipts
  (`run_tracking.py`) + per-run estimated cost from `turn_usage`
  receipts; muted footer ticker on run page. Files:
  `dashboard_web_app.py` (new `/api/runs/{id}/timeline` read),
  `web/app.js`, `tests/test_web_app.py`. Estimate: 5–8h.
- **Owner decision first?** No — read-only surfacing of existing data.

### G5. Fallback happens but is not explained (reliability/fallback UX)

- **User job blocked:** trusting continued work after a route failure —
  what failed, what replaced it, did quality drop, what did it cost.
- **Evidence:** Track B W1 mapped 16 fallback triggers; the trigger
  truth-table, escalation pins (incl. session-scope
  `allow_cost_escalation`), preservation-payload pins and the C1
  doc fix all landed 2026-11-04, leaving G3 (owner call on notice
  semantics), G7 (owner call on default unification; current
  divergence pinned as-is), and a G1 residual check
  `[plans:track-b-20261104.md:6-45]`; dashboard
  run view shows only the fan-out indicator
  ([dashboard_web_app.py](apps/workbench_dashboard/dashboard_web_app.py:53-60)),
  no fallback/quality-downgrade events; ADR-060 receipt fields exist
  but are CLI-rendered, not dashboard-rendered
  ([architecture.md](docs/architecture.md:152-157)).
- **Bounded slice:** (a) remaining W1 pins: G3 pin and G7
  unification pin after the two mailed owner calls, G1 residual
  check ([plans:track-b-20261104.md:32-45]; trigger,
  escalation, preservation and C1 fixes landed 2026-11-04);
  (b) fallback-event feed on the run page from
  existing receipts. Files:
  `tests/test_fallback_*.py` (G1/G3/G7 pins),
  dashboard run view. Estimate: 3–5h.
- **Owner decision first?** Yes for two items — G3 `task_minimum`
  downgrade-notice semantics and G7 fallback-default unification
  (both mailed 2026-11-04, unanswered)
  `[plans:track-b-20261104.md:32-45]`; the rest needs none.

### G6. Single-project dashboard (multi-project/company)

- **User job blocked:** running MORE THAN ONE project — the company will
  have client projects side by side; today the dashboard is bound to one
  workspace with no project choice.
- **Evidence:** `DashboardChat` takes one `workspace` path
  ([dashboard_chat.py](apps/workbench_dashboard/dashboard_chat.py:50-60));
  one `data/` dir, one config; repo/project choice is captured as
  "needs design (6–10h)" and explicitly not a freeze item
  `[plans:backlog.md:20-26]`; owner wants a "repo organization surface"
  as a stepping stone to a project factory
  `[plans:p6-dashboard-proposal.md:128-130]`.
- **Bounded slice (read-only first):** project registry file
  (`data/projects.json`: id, path, display name) + dashboard project
  switcher scoping plans/runs/inbox/chat to per-project data dirs; no
  writes across projects. Files: `dashboard_config.py`,
  `dashboard_stores.py`, `dashboard_web_app.py`, `web/app.js`,
  `tests/test_stores.py`, `tests/test_web_app.py`. Estimate: 6–10h.
- **Owner decision first?** Decided 2026-11-05 ([ADR-082](decisions/ADR-082-centralized-dashboard-no-client-split.md)):
  NO per-client split — runs/inbox/chats/library stay global with
  per-record project refs, since ai-workbench is the primary centralized
  interface. Split only on clear need; second real client project is the
  revisit trigger. (Registry + staged approvals landed via the merge;
  project filters in views still to add. P7 intake-location question
  remains open.)

### G7. Client intake exists only on paper (multi-project/company)

- **User job blocked:** receiving client work — a vague "I want a
  website" becomes a structured brief the owner reviews in <2 minutes
  and hands to Workbench. The P7 format is a proposal; zero code exists.
- **Evidence:** `[plans:p7-project-file-format-proposal.md]` status
  PROPOSED, "No code; doc + JSON schema only"; no validator, no intake
  UI, no chatbot in this tree (verified: no `p7-projects/`, no intake
  module under `apps/` or `packages/`); company work is gated behind
  the offering proposal `[plans:company-offering-draft.md]`, itself
  PROPOSAL ONLY with 11 open owner questions.
- **Bounded slice:** JSON Schema (draft 2020-12) + pure validator CLI
  (`workbench-intake validate FILE` → `{valid, errors, warnings}`),
  including the secrets-reject and PII-flag rules (proposal rules
  12–13), plus dashboard inbox import of valid files. Files: new
  `apps/project_intake/` (schema, validator, CLI), tests incl.
  adversarial secrets/PII cases, dashboard import button. Estimate: 6–8h.
- **Owner decision first?** Yes — P7 Q1/Q2/Q5 (can/cannot-do boundary,
  EUR budget buckets, PII retention) and offering Q1–Q11 gate what the
  validator enforces; build the schema narrowly only after those answers.

### G8. Spend policy unenforced and invisible (reliability + company)

- **User job blocked:** controlling AI spend across runs — free credits
  first, then allowances, prepaid only with permission — especially in
  the Nov 4–9 credit window where P2 evals must not be starved by
  backlog tasks `[plans:product-roadmap-20261031.md:6-18]`.
- **Evidence:** P5 is "PROPOSAL — No code"
  `[plans:p5-spend-policy-proposal.md:1-3]`; no balances, allowances,
  reservations, estimator, or prepaid gate exist (verified: no spend
  module in `ai_orchestrator/`); cost ceiling today is a static default
  (`PREPAID_CREDITS_ALLOWED`, [repo-coding-assistant.md](docs/repo-coding-assistant.md:20-24));
  dashboard has no spend surface (G4 evidence).
- **Bounded slice (read-only first):** spend panel from existing
  `turn_usage`/`account_usage` receipts (per-run, per-day estimated
  cost by bucket) + display of a TOML allowance file; no enforcement.
  Files: `dashboard_web_app.py` (`/api/spend` read),
  `dashboard_stores.py` or new `spend_view.py`, `web/app.js`,
  tests with fixture receipts. Estimate: 4–6h. Enforcement
  (reservation/atomic debit) is a separate, larger slice.
- **Owner decision first?** No for read-only display; yes for
  enforcement — P5 Q1–Q3 (allowance granularity, prepaid-permission UX,
  emergency thresholds) `[plans:p5-spend-policy-proposal.md:117-124]`
  plus offering Q5 (pass-through vs capped allowance).

### G9. No queue or scheduler product surface (daily dev loop + company)

- **User job blocked:** queuing overnight / unattended work and seeing
  what will run when — a company cannot be attended-only.
- **Evidence:** "The scheduler is a foreground, user-started workflow.
  Planned tasks do not start automatically"
  ([repo-coding-assistant.md](docs/repo-coding-assistant.md:55-57));
  `scheduling.py` is admission-only, no background daemon approved
  ([architecture.md](docs/architecture.md:240-251)); dashboard Schedule
  view is a read-only placeholder
  ([README](apps/workbench_dashboard/README.md:44-48)); unattended
  scripts (`scripts/unattended-development-loop.py`,
  `scripts/meta-develop.py`) exist but are operator-run, not
  productized or dashboard-visible.
- **Bounded slice:** wire the dashboard Schedule view to the existing
  foreground `task_scheduler` store (list planned/waiting tasks,
  read-only) + a "start window" action that prints/shells the exact
  existing foreground CLI command — no new daemon. Files:
  `dashboard_web_app.py`, `web/app.js`, tests. Estimate: 5–8h.
- **Owner decision first?** No while foreground-only; YES the moment
  anyone proposes a daemon, background service, or auto-start —
  that is a material AGENTS.md decision
  ([AGENTS.md](AGENTS.md:64-66)).

### G10. No final-report artifact (daily dev loop + docs)

- **User job blocked:** reviewing and handing over completed work — the
  P1 "final report presents decisions" deliverable with fixed sections
  `[plans:p4-agent-ux-proposal.md:48-52]`.
- **Evidence:** no report template or generator exists (verified: no
  report module under `apps/workbench_dashboard/` or `ai_agent/`;
  `external_reporting.py` covers delegated-source rendering, not the
  P1 report); P4 rec 5 ("ship final-report template, live preview")
  unimplemented `[plans:p4-agent-ux-proposal.md:81]`; run
  `report` field is only requested via an inbox task
  ([dashboard_web_app.py](apps/workbench_dashboard/dashboard_web_app.py:447-476)).
- **Bounded slice:** report generator from run receipts → Markdown with
  fixed sections (Objective, Plan executed, Decisions, Small fixes,
  Big-change proposals, Verification, Next steps) + dashboard preview
  and download. Files: new `apps/workbench_dashboard/report.py`,
  web wiring, `tests/test_report.py` (golden-file test). Estimate: 3–5h.
- **Owner decision first?** Yes, one question — P4 Q5 report audience
  (owner-only vs recruiter-visible/sanitized)
  `[plans:p4-agent-ux-proposal.md:101-107]` determines content rules.

### G11. Owner-task inbox cannot reach an away owner (visibility)

- **User job blocked:** answering decisions/clarifications when away
  from the desk — runs stall on owner input with badge-only notification.
- **Evidence:** "no push in v1; badge + Home widget only"
  `[plans:p6-dashboard-proposal.md:82-89]`; inbox flow has no notify
  step in code ([dashboard_web_app.py](apps/workbench_dashboard/dashboard_web_app.py:343-397));
  the `operator_bridge` phone-push path exists
  ([operator_bridge.py](packages/ai_agent/src/ai_agent/operator_bridge.py))
  but the dashboard does not use it.
- **Bounded slice:** on inbox-task creation, best-effort push via the
  existing `OperatorApprovalBridge` (metadata-only descriptions per
  ADR-075); failure degrades to badge-only with a visible receipt.
  Files: `dashboard_stores.py` or new `inbox_notify.py`,
  `tests/test_inbox_notify.py` (fake bridge). Estimate: 4–6h.
- **Owner decision first?** Small yes — reuses the approved bridge, but
  owner should confirm push-on-create vs digest, and phone remains the
  remote-operator thin client per P3 (no product logic move).

### G12. No company-run documentation (docs gaps)

- **User job blocked:** learning "how we run a client project here" —
  intake → plan → execute → verify → report → invoice inputs — as one
  Sky-high doc instead of 30+ scattered workflow pages.
- **Evidence:** `docs/repo-assistant/` holds 30+ pages but no
  end-to-end company run; dashboard user docs are a 50-line README
  ([README](apps/workbench_dashboard/README.md)); no troubleshooting/FAQ
  (common failures — Ollama down, allowance exhausted, token expiry —
  are documented per-adapter at best); product/company plans live in
  gitignored `[plans]` invisible to the dashboard and to fresh clones.
- **Bounded slice:** `docs/company-run.md` (intake→report→handoff
  checklist with commands) + dashboard "Help" page rendering the
  troubleshooting subset + inbox/report cross-links. Files:
  `docs/company-run.md`, `web/index.html` help section, link test.
  Estimate: 3–4h.
- **Owner decision first?** No for structure; content for intake/pricing
  sections inherits G7/G8 owner answers — write with placeholders.

## Cross-cutting notes

- **Total bounded-slice load:** ~55–84h across G1–G12 (all slices
  independently shippable; stop after any one and keep the value).
- **Recurring owner-decision themes** (answer once, unblock many):
  P4 approval/steering granularity, P5 allowance + prepaid UX, P7
  intake/budget/PII rules, offering lines/pricing/IP, report audience.
- **Do-not-build reminders from the plans:** no per-tool approval
  modals, no raw-command streaming as primary view, no mid-tool kill,
  no autonomous big-change execution, no daemon/scheduler before its
  decision, no template system before P7 exists (P8 correctly ordered
  greenfield `[plans:p8-templates-scouting.md]`).
