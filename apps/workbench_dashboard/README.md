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
  (`data/chats.sqlite3`). Turns cannot run tools yet — the assistant
  says what it would do instead of claiming effects.
- Plans/Runs: read-only views of file-backed `data/plans/` and
  `data/runs/` records created by existing Workbench flows.
- Inbox: decisions/clarifications assigned to the owner; answers flow
  back as record updates. Creation requires the supervisor token when
  `data/supervisor.token` exists.
- Feedback standard: every action shows a visible receipt — success,
  progress, or the exact error. Silent no-ops are defects.

## Limits (honest)

- Chat answers are single-shot completions, not agent runs: no tools,
  no approvals, no delegation yet.
- Schedule is a read-only placeholder until the P5 scheduler exists.
- Helper-process inventory deepens with the P5 queue; v1 lists runs,
  plans, inbox, and route evidence.
- Backend defaults to local Ollama; hosted providers need their usual
  environment credentials and explicit privacy choice.
