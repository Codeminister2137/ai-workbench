# Chatbot directions — owner planning brief (2026-11-01)

Worker-drafted research brief, verified by the parent agent against the
roadmap and code. Owner decision recorded below.

## Owner decision (2026-11-01, chat)

Agreed with the recommendation, with one correction and one ordering fix:

- Correction: "anything built in the operator is throwaway or needs
  porting" is too harsh. Remote-operator will be transformed somewhat
  after the hackathon anyway; while the hackathon runs, building there
  is fine whenever something fits better there than in ai-workbench.
  A stronger competition submission is worth blurry post-hackathon
  ownership.
- Order: B first, then A. D as a mode inside B. C held for P7/plan-04.
- Future dashboard note (owner): multi-monitor support eventually -
  feasible in a web app via separate windows over the shared backend;
  not now.

## Inputs read

- Private plans (read-only, main checkout `docs/plans/`, git-ignored):
  `00` master checklist, `01` provider-agnostic infrastructure,
  `02` local AI Council, `04` IT-services business start (PL).
  This brief stays high-level; plan details are not copied here.
- Tracked context: [project-map](project-map.md) (Future AI Dashboard /
  General Chat), [ideas](ideas.md) (Provider/Orchestrator Dashboard),
  private product roadmap 2026-10-31 (P1, P3, P6, P7),
  P6 dashboard proposal, P7 company scouting +
  project-file-format proposal.
- `apps/ai_council`: README, `council.py`, `agent.py`, `web_app.py`
  (multi-member Ollama respondents, SSE streaming, SQLite history,
  loopback-only browser UI).
- Workbench chat atoms: `docs/repo-assistant/chat.md` (persistent
  provider-neutral transcripts), `coding-chat.md` + ADR-049 (continuous
  coding chat with tools/permissions).
- Remote-operator chat UI (READ ONLY, separate repo
  `remote-ai-operator`, never modified): README, `src/remote_operator/`
  (`web.py` supervisor/external-action routes, `index.html` chat-first
  sections, `app.js` thread/transcript functions), supervisor-thread +
  run-settings + review/approve flow.

Key constraints inherited from those inputs:

- Roadmap correction (2026-10-31): ai-workbench is the owner's product;
  remote-operator is the competition repo. Post-hackathon product work
  must NOT live in remote-operator. Operator stays relevant only as a
  P3 thin client via the existing bridge.
- Plan-04 gates: no business chatbot before validation (problem → offer →
  payment → delivery → economics → setup). Selling "AI agents" is not a
  value proposition; sell a measurable outcome.
- Ideas/dashboard hard constraints: chat surface must not own provider
  APIs or orchestration policy; cloud use needs explicit privacy
  controls; transcripts stay provider-neutral and local.

## Option A — Extend the operator chat (supervisor threads)

Grow the existing chat-first phone UI in remote-operator: richer
supervisor threads, more run control, more review actions.

- Users: owner on phone (remote supervision); hackathon judges/visitors
  in hosted mode.
- Surface: operator served UI section "1 · Chat" (threads, transcript,
  plan, runs) + run-settings + review/approve, over
  `/api/supervisor/threads`, `/api/supervisor/runs`, `/api/tasks`,
  `/api/external-actions`.
- Data it touches: `.runtime` task state, supervisor threads/runs,
  approval nonces, allowance/grant records, sample import results.
- Reuses: `web.py`, `supervisor.py`, `supervisor_runner.py`,
  `index.html`/`app.js`, hosted session/auth slice, Modal deployment.
- Dependencies: operator bridge (P3) for any Workbench-backed
  execution; judge-grant/hosting limits for spend; phone-access HTTPS
  setup for real remote use.
- Effort: M (the chat shell exists; each new capability is a
  supervised slice with tests + browser smoke).

Pros:

1. The only phone-ready chat surface that exists today: served UI,
   hosted visitor/judge mode, and approval flows are implemented and
   live-verified, including on a physical phone.
2. Cheapest path to remote P1 loop UX: threads, `waiting_on_owner`
   parking, run settings, and exact-change approval already match the
   supervised-loop shape.

Cons:

1. Directly conflicts with the roadmap correction: new product code in
   the competition repo is explicitly out of scope post-hackathon, so
   anything built here is throwaway or needs porting to ai-workbench.
2. The actor model is wrong for general chat: scripted reference by
   default, Meta-only live path with finite grants — no provider
   choice, no privacy classes, no orchestrator routing.
3. Approval-window/task framing fits supervised coding runs, not open
   conversation; bending it into a general chatbot fights the design.

## Option B — Standalone local chat in ai-workbench (P6 dashboard chat)

Build the general-chat surface inside ai-workbench as the P6 dashboard
"Chat" view (or a thin precursor): chat with the supervisor, routed to
a better-placed agent when applicable. This is the "replace a share of
day-to-day ChatGPT usage" surface from ideas.md.

- Users: owner (daily driver: research, planning, shopping/workout
  decisions, project planning, coding help).
- Surface: local browser UI, new `apps/workbench_dashboard/` per the P6
  proposal (council pattern: stdlib HTTP, static files, hash routing);
  later phone via Tailscale (stretch, not v1).
- Data it touches: provider-neutral transcripts (SQLite, local-only),
  plans/runs/evidence/inbox stores under `data/dashboard/`
  (read-only except chat + inbox answers).
- Reuses: `apps/ai_council` web pattern (`web_app.py` + `web/`);
  `ai_agent/coding_chat.py` + `loop.py` chat/turn atoms;
  `ai_provider` backends (Ollama local, Requesty, direct hosted);
  `ai_orchestrator` routing/refinement; `operator_bridge.py` for
  phone push later.
- Dependencies: P6 owner answers (surface priority, inbox scope,
  chat-routing rule); model-quality evidence (local vs hosted per task
  class) before claiming ChatGPT replacement.
- Effort: M (thin wrapper + UI over proven atoms; no new chat stack,
  no new framework/DB/auth in v1).

Pros:

1. Lives in the right repo and on the right architecture: local-first,
   privacy classes (LOCAL/CLOUD/HYBRID), provider-neutral transcripts,
   orchestrator routing — all already decided and partly built.
2. Directly serves P1/P6: the same chat view becomes supervisor chat,
   inbox answers, and plan/run review, instead of a one-off demo page.

Cons:

1. No phone story in v1: local browser only, so remote use waits on
   Tailscale or the P3 operator thin client — the highest-friction gap
   versus Option A.
2. Model-quality risk is not yet de-risked: no evidence yet that local (or
   cost-capped) models clear the "good enough to replace ChatGPT"
   bar per task class; the eval work (P2/L2) is the critical path.
3. Scope-creep magnet: dashboard, inbox, schedule, and workflow
   builder all want to pile into v1; needs the P6 non-goals list
   enforced to stay an M.

## Option C — Company website chatbot (P7 intake bot, plan-04 pains)

Customer-facing bot on the future company site: aware of site content
plus a knowledge bank of what the company can/cannot do; guides vague
requests ("I want a website") through questions into a shared project
file the owner hands to Workbench. Directly the P7 roadmap item, fed
by plan-04 validation pains (customer inquiries, repetitive manual
intake, scoping).

- Users: site visitors (prospects); owner as reviewer/gate before any
  Workbench intake.
- Surface: website chat widget → guided-question flow → one JSON
  project file per inquiry (`p7-projects/<slug>-<date>-<id>.json`,
  format v1.0.0 already proposed with validation rules).
- Data it touches: site content + capability knowledge bank
  (file-based first); inquiry project files containing client PII
  (name/email/company/phone) — GDPR controller/processor roles,
  retention, and consent required before processing.
- Reuses: council static-serving + JSON API pattern (NOT its
  localhost-trust model — public hosting is a separate decision);
  `ai_agent/loop.py` multi-turn atoms as a reference (untrusted-input
  cousin, new surface); `ai_orchestrator/planner.py` plan-shape
  precedent; P7 project-file format proposal as the handoff contract.
- Dependencies: blocked on P7 owner answers first — company name,
  services, can/cannot-do boundaries, website stack/hosting, chatbot
  model + budget + abuse guardrails; plus plan-04 validation gates
  (recurring problem → paid pilot) before it earns engineering time.
- Effort: L end-to-end (M for bot + knowledge bank once brief/hosting/
  model decisions exist; S for the file-format slice, already drafted).

Pros:

1. Only option with a direct revenue path: every conversation can end
   in a structured, owner-reviewable sales intake instead of an
   unanswered contact form.
2. Handoff contract already designed: closed JSON schema, validation
   rules, secrets/PII guards, owner gate, immutable-after-approval —
   so the bot's output is actionable by construction.

Cons:

1. Blocked on business decisions, not engineering: no name, services,
   site, or hosting exists, and plan-04 says code before validation
   is speculative — building now risks a bot for a company that never
   ships.
2. Public-surface burden: abuse limits, cost caps per session,
   prompt-injection resistance on untrusted input, GDPR/retention,
   uptime — none of which local-chat options pay.
3. Knowledge-bank maintenance is an ongoing content job: stale
   can/cannot-do entries make the bot mis-sell; needs an update
   workflow, not just a build.

## Option D — Council-fronted chat (multi-model chat + synthesis)

Turn the AI Council into a conversational front end: each user turn
goes to N configured respondents in parallel, then a synthesis step
separates agreement, disagreement, assumptions, minority claims, and
uncertainty — the plan-02 Phase 2 behavior exposed as chat.

- Users: owner, for ambiguous or high-stakes questions where
  disagreement is informative (architecture choices, planning,
  second opinions); explicitly NOT the default for simple tasks.
- Surface: council browser UI extended with a synthesis pane
  (agreement/disagreement/assumptions/minority/synthesis sections),
  or a "council mode" inside the Option B chat view; CLI keeps the
  bypass path (`tasks.ps1 cli`).
- Data it touches: same as council today — `data/council.sqlite3`
  (prompts + raw answers, private), `council.json` member config;
  synthesis adds derived rows, raw answers stay preserved.
- Reuses: `council.py` respondents + `ask_events` streaming,
  `agent.py` provider-backed members, `storage.py` history,
  `web_app.py` + `web/` UI; orchestrator later for respondent
  selection (plan-02 Phase 3, not v1).
- Dependencies: synthesis prompt/format design + minority-visibility
  tests (plan-02 acceptance); provider expansion beyond Ollama-only
  members for real model diversity; Council-vs-single eval rule
  (plan-02 Phase 4) to trigger it only when worth it.
- Effort: S for a first synthesis pass over existing respondents
  (one more model call + UI pane + tests); M with orchestrator
  respondent selection + eval harness.

Pros:

1. Smallest build on the most complete base: respondents, streaming,
   storage, and UI all exist and are tested — synthesis is one
   additive step, and raw-answer provenance is already the design.
2. Genuinely differentiated: no hosted chatbot shows its disagreement;
   minority-preserving synthesis is the Council's reason to exist and
   the one thing ChatGPT cannot do.

Cons:

1. 3x latency/cost per turn (plus synthesis) makes it the worst
   default: without the Phase 4 trigger rule it will feel slow and
   wasteful on exactly the simple questions asked most often.
2. Local-model diversity is shallow today: three Ollama members often
   share failure modes, so "independent viewpoints" can be an
   illusion until cloud/hybrid respondents arrive with privacy modes.
3. Synthesis quality is unproven: a weak synthesizer hides the
   minority view the Council exists to preserve — the critical design
   question in plan-02, still open.

## UNREVIEWED DRAFT — worker technical lean (parent to verify)

This section is a worker-drafted opinion, NOT reviewed. Parent will
verify before presenting to the owner.

Lean: B first (thin P6 chat slice in ai-workbench), D as a mode inside
B, C gated on P7/plan-04 decisions, A frozen except P3 thin-client
duty.

- Start B as the smallest chat view that reuses `coding_chat` atoms +
  council web pattern against existing providers. It compounds toward
  P1/P6; A cannot compound because it lives in the wrong repo.
- Add D as an explicit "ask the council" mode of the same chat view
  rather than a separate product: shared transcripts, shared UI,
  bypass-by-default honors plan-02's exit criteria.
- Hold C until the owner answers P7 questions 1–3 AND plan-04 shows a
  validated problem; the project-file format (already proposed) is
  the right artifact to finalize meanwhile since it is pure doc.
- Keep A to P3 bridge work only: operator chat as remote thin client
  with Workbench behind it, no new operator-owned chat features.

Suggested owner questions: (1) confirm B-local-first vs any remote
need that forces A sooner; (2) pick the first ChatGPT-replacement
task class to evaluate for B; (3) answer P7 Q1–Q3 or explicitly park
C; (4) confirm D-as-mode vs standalone council UI.

## Owner directions (2026-11-01, chat)

Decided this session: B1 (coding help) is the first B slice; B2/B3
(research/planning, daily misc) follow later — they fit owner use more
but B1 is the measurable first slice. P6 phased v1/v2/v3 confirmed.

Security requirements for the company-site bot (C), recorded for its
future workstream (P7/plan-04 gates still apply):

- Purpose confinement: users can only use the bot for its intended
  intake purpose, not as a general assistant.
- Jailbreak resistance including social-engineering and
  emotional-manipulation attempts ("stupid attacks" that work count).
- No protected-data or cross-user-data leakage under any prompt story.
- Design implication: system-prompt hardening alone is insufficient;
  C needs capability sandboxing (narrow tools, no raw data access),
  session isolation between visitors, and a red-team eval slice before
  any public exposure.

Operator chatbot direction: a UI copilot that explains which UI action
achieves the owner's goal ("which button for X"), complementing
tooltips; ideally also able to act for the user as a less-manual
interaction mode. OPEN: acting for the user must not bypass the
operator's exact-change approval boundary. Recommendation recorded:
guidance-only v1; any bot-proposed action flows through the normal
approval UI with the bot as proposer, never approver. Awaiting owner
confirmation or an alternative line.

Hosted-model tiering research (both hosted bots): public models need a
quality floor but simple tasks must not burn frontier models. This is
P2/L3 program work: per-task-class quality/cost frontiers measured by
the L3 ladder, producing a tiering policy. Approved inside eval scope.

Workbench bot: complex management of various code is the priority.
The owner's message was truncated mid-sentence ("no..."); the
completion is an open question, not an assumed requirement.
