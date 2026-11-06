# Workbench Dashboard (P6 v1 slice A)

Local-first supervisor dashboard: status-at-a-glance, chat with the
supervisor, plans, runs, and the owner-task inbox. Stdlib HTTP on
loopback only (council pattern); no new framework, DB, or auth.

## Run

From `apps\workbench_dashboard`:

```powershell
.\tasks.ps1 init
.\tasks.ps1 start
```

Open `http://127.0.0.1:8766` in a browser.

`init` copies `dashboard.example.json` to the private local
`dashboard.json`. `start` refuses to double-start; `stop` and `status`
inspect the owned process only.

## What v1 does

- Home: backend, active plan, recent runs, evidence counts, inbox count,
  chat quick-entry. Every list is one click away; items cross-link.
- Chat: supervisor answers with full local transcripts
  (`data/chats.sqlite3`). Turns stay tool-less, but any message can be
  queued as an agent run (Request run, optional project scope): the run
  lands in `data/runs/` as `queued` with fan-out `restricted` unless
  `chat_fanout_policy` says otherwise, an inbox approval decision is
  created, and the thread keeps a system receipt. Nothing executes
  until the owner approves and a worker drains the queue.
- Plans/Runs: plans carry a phase checklist and an approve/reject flow;
  runs show live status, events/receipts, Did/Found/Next synthesis, and
  one fan-out indicator (allowed/restricted/denied, or unknown for
  records that predate the field). Project-scoped runs show staged
  diffs for review with approve-and-apply.
- Inbox: decisions/clarifications assigned to the owner; answers flow
  back as record updates. Creation requires the supervisor token when
  `data/supervisor.token` exists. The nav badge is a live open count.
- Voice/language: the chat Dictate button posts microphone clips to
  `POST /api/stt/transcribe`; messages accept a `language` tag and
  translate at ingestion with source provenance. Both fail closed
  (409) until a keyed engine, metering, and translator are wired.
- Documents: company library over `docs/library/` (tracked, public),
  `docs/plans/` (private, read-only), and `docs/library-private/`
  (private, gitignored default for new research). Markdown previews
  in-tab; every file opens with one click (browser or download).
- Ideas: fast capture inbox for brain-dumps, tagged `owner` or
  `third-party` (with optional contact); triage to
  reviewing/adopted/parked/declined with a decision note.
- Owner mail: terminal run outcomes can notify the owner by email.
  Set `WORKBENCH_OWNER_EMAIL` + `WORKBENCH_SMTP_HOST` (plus optional
  `_PORT`/`_USER`/`_PASS`/`_STARTTLS`) in the environment, or just
  `GMAIL_EMAIL` + `GMAIL_PASSWORD` (env or root `.env`, Gmail SMTP); without
  them the notifier stays silent. Delivery is fail-closed to the
  owner address only, with a receipt per send. `supervision` in
  `dashboard.json` (`attended` default, or `unattended`, switchable
  via `GET`/`POST /api/settings`) selects whether only
  failed/waiting runs mail, or every terminal outcome does.
- Feedback standard: every action shows a visible receipt — success,
  progress, or the exact error. Silent no-ops are defects.
- Agent status: `GET /api/agent-status` reports what the agent is
  working on from the gitignored `window-status.json` heartbeat at
  the checkout root; a missing file reads as idle.
- Agent executor: drained runs execute through `AgentLoop` with the
  full coding toolset (read/search/git/shell/python/navigate plus
  staged writes, one-level `delegate_task` subagents, and
  `request_owner_task` human tasks). Project file changes stage into
  the run record for owner review/apply; human tasks land in the
  inbox; shell and Python run unconfined under the per-run approval
  (owner decision). Child fan-out follows the run policy; child
  staged files carry back into the parent receipt.

## Limits (honest)

- Runs drain manually (Runs "Drain now" / `POST /api/runs/drain`,
  one run per call) or on a schedule (`drain_interval_seconds` ≥ 60
  in `dashboard.json` + restart; default off). No UI/API toggle yet;
  one run per tick; tick failures are logged, not mailed.
- Transcription/translation need owner-wired keys and metering; the
  endpoints answer 409 until then. No per-project data isolation yet:
  runs/inbox stay global with per-run project refs (G6 owner question).
- Schedule is a read-only placeholder until the P5 scheduler exists.
- Helper-process inventory deepens with the P5 queue; v1 lists runs,
  plans, inbox, and route evidence.
- Backend defaults to local Ollama; hosted providers need their usual
  environment credentials and explicit privacy choice.
