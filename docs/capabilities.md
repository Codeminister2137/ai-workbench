# Workbench capabilities ledger

What exists, what works, and what each piece needs. No secrets here —
only variable *names* and credential *status*, never values. Update this
file when a slice adds, removes, or changes a capability (proposed
Definition-of-Done rule, pending owner approval).

Last verified: 2026-11-06 evening (Baseten loop: drain@300 live, 7 REAL audit items resolved, 7 UNREVIEWED fixed, inbox decisions implemented).

## One command

- `.\serve.cmd` (repo root) → `scripts/serve-all.ps1`: starts dashboard
  `:8766`, Ollama `:11434`, and the tailnet mapping; verifies each.
  Append new services as one entry in `$services`.

## Local services

| Service | Address | Status | Notes |
|---|---|---|---|
| Dashboard | `http://127.0.0.1:8766` | up | localhost-only by design; remote via tailnet |
| Remote dashboard | `https://<your-machine>.<your-tailnet>.ts.net` | up | `tailscale serve`; needs `trusted_hosts` in live `dashboard.json`; find your URL via `tailscale status --json` (`.Self.DNSName`) |
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
| `ollama/gpt-oss:20b` | local runtime, 64k budget | implement-mode runs; 8-turn probe 8/8 clean post-slim (overflow resolved) |
| `ollama/qwen3:14b` | local runtime | tools-capable; 4k budget (too small for implement) |
| `openai/codex-gpt-6.1-sol` | `codex` CLI 0.166.0 (PATH), ChatGPT login | verified `completed` — spend freely |
| `meta/muse-spark-1.3` | provider API | wired; re-probed 200 on 2026-11-06 (outage was local MSI fallout) |
| `baseten/muse-spark-open-1026` | `BASETEN_HACKATHON_API_KEY` event key | loop-proven 2026-11-06 (9 slices); verbose — caps: 2k probes / 16k code; needs host review (strays) |
| requesty/openrouter/modal | provider APIs | wired; keys in `.env` (names only, see `.env.example`) |

Codex note: PyCharm-bundled 0.137.0 is too stale (400s); PATH 0.166.0 wins.
Spend order D1 (owner, till ~Nov10): Baseten > Modal-if-possible > Meta > Codex. Modal inference NOT possible (no deployed endpoint; only the mgmt key).

## Dashboard chat (supervisor)

- Relay turns with inspection tools (read/list/search, git status) plus
  visible receipts; writes and execution stay approval-gated.
- System prompt grounded 2026-11-05: no mail/service claims, no Linux paths.
- Request-run queues approval-gated runs; transcript scope: capped digest
  (30 turns / 500 chars) + session ref, attachments surfaced.
- Slim supervisor instructions (2026-11-06): static prompt 872→581 chars
  (600-char budget, asserted); per-delegation assembly adds only receipts /
  policy / paths; long-form guidance moved to `docs/supervisor-handbook.md`
  (reference-only, never sent). Overflow re-measured 2026-11-06: 8/8
  history-growing turns clean (6–26s).
- Chat-channel tools (2026-11-06): `get_run_status`, `list_pending_inbox`
  (id+type+title only, no bodies/secrets), `read_dashboard_doc` (4k cap).
  Read-only, fail-closed, visible receipts; executor registry untouched.
- Drain worker v1 (2026-11-06): `POST /api/runs/drain` executes approved
  runs oldest-first (`max_runs`, default 1); "Drain now" button on Runs;
  E2E proven approve→drain→completed on live server.
- Drain scheduler v1 (2026-11-06): owner voted ENABLE at 300s; live and ticking; state on /api/status (started/ticks/errors).
  Code default stays OFF; live `dashboard.json` carries 300. No UI toggle yet.
- Empty-answer fallback (2026-11-06): blank model content now yields a
  receipt summary instead of an empty reply + bare receipts (owner report).
- Restart protocol: check chat for recent activity before restarting the
  dashboard — a restart raced an owner turn on 2026-11-06 (HTTP 502).

## Delegation (supervisor creates/runs agents)

- `delegate_task`: one level deep, narrowed registry/permissions/paths,
  shared reply+tool budget, staged files carry back to the parent receipt.
- Per-task model routing (2026-11-06): supervisor may request a child
  model per call; host allowlist + client factory; unknown/unconfigured
  models refused fail-closed. E2E parent-loop test green.
- Blank-handling contract: the loop returns what the model says; callers
  decide — native wrapper rejects blanks (ProviderError), messenger falls
  back to a receipt summary. (A loop-level retry was tried and reverted
  2026-11-06: it broke 6 pinned tests; see plan file.)
- Backlog: executor path silently accepts blank final summaries
  (no observed failure; reject-vs-fallback needs owner input).

## Mail (unified credential, two transports)

- One credential: `GMAIL_EMAIL`/`GMAIL_PASSWORD` in root `.env`
  (verified + live-tested 2026-11-06). Legacy job-email `.env` deleted.
- `scripts/loop_notify.py`: stdlib SMTP since 2026-11-06 (decision A cutover);
  receipted pings, 3× retry. `sender.py` stays the job-search transport only.
- `apps/workbench_dashboard/owner_mail.py`: stdlib SMTP; falls back to
  the `GMAIL_*` pair (env, then root `.env`) when `WORKBENCH_*` absent.
- Transport decision CLOSED 2026-11-06 (owner chose A): canonical = stdlib
  `owner_mail`; notifier cut over, sender-unify tests updated.

## Documents + research (private, gitignored)

- Dashboard Documents tab serves `docs/library-private/` (services-by-effort,
  pricing-global-local, pricing-lowend-threat, advertising,
  msi-uninstall-safety), `docs/plans/`, proposals. Markdown
  previews render in-tab; one-click file open.
- Market correction 2026-11-06: HU/HUF artifacts fixed to PL/PLN; website-line
  bands under owner deliberation (~500 PLN observed floor).
- Low-end threat study 2026-11-06: 70+ datapoints; 500 PLN tier is
  template/AI product, market bifurcating; lean avoid + rescue-care.
- MSI note 2026-11-06: removal safe via staged path; LAN Manager flagged
  second network suspect; removal itself = owner decision.
- R2 name evaluation 2026-11-06: `codeministry-name-evaluation-20261106` —
  verdict NO-GO (5 same-market EU/UK users); Kodministerstwo / Code
  Chancellery smoke-clear; surname pattern safest. 76 docs served.

## Dashboard UI (2026-11-06)

- Restrictions tab: read-only overview of 6 agent-restriction dimensions;
  no enforcement source of truth exists, so all show honest
  `not yet evaluated` + feeder (10 nav links, 42 UI tests green).
- Ollama context sizing: adaptive chat tiers 8/16/32k + executor 32k
  (was 4k default truncating 14.6k prompts — the SeerX/OpenRouter
  confabulation root cause).

## Audit triage (2026-11-06 Baseten loop)

- REAL — POST-HACKATHON: 0 (was 7; 6 pre-fixed verified, body-bounds fixed in-loop).
- UNREVIEWED: 156 (was 176; /0+/2 batches triaged, 7 fixed with tests).
- Watcher consoles hidden (task + script); stale token-gate comment corrected 
  (tailnet-membership trust, single-user).

## Grants (remote-operator — deprecated path)

- Local operator serve: DEPRECATED, verified not running. Do not revive.
- Modal hosted deployment: must stay up, untouched, until 2026-11-10.
- Owner inference-grant renewal: NOT NEEDED (deprecated path). No action.

## Known gaps (see inbox + todos for live state)

- P7 answers (owner deliberating; pricing part informed by threat study),
  MSI removal (owner decision), naming (owner voted DEFER),
  executor blank-summary backlog, live Meta delegation E2E (route proven, E2E pending).
