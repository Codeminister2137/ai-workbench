# Workbench capabilities ledger

What exists, what works, and what each piece needs. No secrets here —
only variable *names* and credential *status*, never values. Update this
file when a slice adds, removes, or changes a capability (proposed
Definition-of-Done rule, pending owner approval).

Last verified: 2026-11-06 ~11:00 (steps 4+5 merged, chat smoke live).

## One command

- `.\serve.cmd` (repo root) → `scripts/serve-all.ps1`: starts dashboard
  `:8766`, Ollama `:11434`, and the tailnet mapping; verifies each.
  Append new services as one entry in `$services`.

## Local services

| Service | Address | Status | Notes |
|---|---|---|---|
| Dashboard | `http://127.0.0.1:8766` | up | localhost-only by design; remote via tailnet |
| Remote dashboard | `https://desktop-j2m5erf.tailc59785.ts.net` | up | `tailscale serve`; needs `trusted_hosts` in live `dashboard.json` |
| Ollama | `http://127.0.0.1:11434` | up | models: gpt-oss:20b, qwen3:14b, qwen2.5-coder:14b, deepseek-coder-v2:16b |

## Scheduled tasks (machine-local, scripts committed)

| Task | Every | Rights | Script |
|---|---|---|---|
| WorkbenchDashboard | 5 min | user | restarts dashboard + Ollama when probes fail |
| MsiUdpWatchdog | 5 min | elevated | restarts MSI service above 2,000 UDP endpoints; logs to `.tmp/msi-watchdog/incidents.log` |
| UDPPortExhaustionTrap | on Tcpip 4266 | system | capture-only UDP snapshot to `.tmp/udp-trap/trap.log` |

Register: `scripts/register-watchdog-tasks.ps1` (elevated).
Remove: `Unregister-ScheduledTask -TaskName WorkbenchDashboard,MsiUdpWatchdog -Confirm:$false`.

## Agent routes (`ai-assistant`, default catalog)

| Route | Access | Status 2026-11-06 |
|---|---|---|
| `ollama/gpt-oss:20b` | local runtime, 64k budget | implement-mode runs; multi-turn overflows (slim fix queued) |
| `ollama/qwen3:14b` | local runtime | tools-capable; 4k budget (too small for implement) |
| `openai/codex-gpt-6.1-sol` | `codex` CLI 0.166.0 (PATH), ChatGPT login | verified `completed` — spend freely |
| `meta/muse-spark-1.3` | provider API | wired; needs reachability re-probe after network outage |
| requesty/openrouter/modal | provider APIs | wired; keys in `.env` (names only, see `.env.example`) |

Codex note: PyCharm-bundled 0.137.0 is too stale (400s); PATH 0.166.0 wins.

## Dashboard chat (supervisor)

- Relay turns with inspection tools (read/list/search, git status) plus
  visible receipts; writes and execution stay approval-gated.
- System prompt grounded 2026-11-05: no mail/service claims, no Linux paths.
- Request-run queues approval-gated runs; transcript scope: capped digest
  (30 turns / 500 chars) + session ref, attachments surfaced.
- Slim supervisor instructions (2026-11-06): static prompt 872→581 chars
  (600-char budget, asserted); per-delegation assembly adds only receipts /
  policy / paths; long-form guidance moved to `docs/supervisor-handbook.md`
  (reference-only, never sent). Multi-turn overflow risk reduced, not yet
  re-measured under load.
- Chat-channel tools (2026-11-06): `get_run_status`, `list_pending_inbox`
  (id+type+title only, no bodies/secrets), `read_dashboard_doc` (4k cap).
  Read-only, fail-closed, visible receipts; executor registry untouched.
- Drain worker v1 (2026-11-06): `POST /api/runs/drain` executes approved
  runs oldest-first (`max_runs`, default 1); "Drain now" button on Runs;
  E2E proven approve→drain→completed on live server. No scheduler yet —
  one click/shot per call.

## Mail (two call-sites, one missing credential)

- `scripts/loop_notify.py`: Gmail app password (`GMAIL_EMAIL`, `GMAIL_PASSWORD`
  in `.env`), receipted pings to owner only. Went LIVE before; credential
  currently absent — owner re-adding 2026-11-06, then delivery test.
- `apps/workbench_dashboard/owner_mail.py`: SMTP (`WORKBENCH_SMTP_*`), receipted.
  Uncredentialed. Unification decision: point at Gmail SMTP once creds land.
- Legacy `.env` at `apps/job_search/job-email/.env`: delete after move verified.

## Documents + research (private, gitignored)

- Dashboard Documents tab serves `docs/library-private/` (services-by-effort,
  pricing-global-local, advertising), `docs/plans/`, proposals. Markdown
  previews render in-tab; one-click file open.
- Market correction 2026-11-06: HU/HUF artifacts fixed to PL/PLN; website-line
  bands under owner deliberation (~500 PLN observed floor).

## Grants (remote-operator — deprecated path)

- Local operator serve: DEPRECATED, verified not running. Do not revive.
- Modal hosted deployment: must stay up, untouched, until 2026-11-10.
- Owner inference-grant renewal: NOT NEEDED (deprecated path). No action.

## Known gaps (see inbox + todos for live state)

- P7 answers (owner deliberating — research correction folded in),
  mail credential + unification, MSI uninstall safety research (after data).
  Drain has no scheduler yet.
