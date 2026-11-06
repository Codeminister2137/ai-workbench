# Pivot redundancy / automation audit — 2026-11-06

Scope: ai-workbench repo. Method: measured overlap (non-blank shared
lines), import/call-site inspection, read-only analysis during the
2026-11-06 evening unattended window. Owner decisions queued to the
dashboard inbox (mail-inbox tandem); nothing below was implemented
without approval except the marked small host fix.

## Confirmed redundancies (owner decision needed)

### R1 — `.env` parsing duplicated in 8 scripts

`alternate-agent-acceptance.py` (`load_dotenv_secrets`),
`baseten-supervised-develop.py` (`read_key`),
`baseten-slice-develop.py`, `loop_notify.py` (`_read_env_file`),
`meta-develop.py` (`read_meta_key_file`),
`meta-supervised-develop.py`, `plan-with-supervisor.py`,
`unattended-development-loop.py` (`read_event_key`) each hand-parse
`.env` instead of using `ai_provider.secrets`. The venv has editable
installs so scripts CAN import it (`meta-develop` already imports
`ai_agent`). Drift already caused real bugs (dotenv export-strip W3,
missing-.env W4a).

Proposal: add `read_secret_key(path, name)` to `secrets.py`; migrate
one script per commit with tests. Inbox brief queued
(`Decision: unify .env parsing in scripts?`, recommending yes).

### R2 — baseten-supervised vs meta-supervised share ~37%

105/289 non-blank lines shared between
`scripts/baseten-supervised-develop.py` and
`scripts/meta-supervised-develop.py` (prompt build, phase loop,
receipt shape). Both stay live under spend order D1
(Baseten > Modal-if-possible > Meta > Codex).

Proposal: extract ONLY the identical blocks (receipt + phase loop)
into a narrow shared core; leave provider prompts in each driver.
Inbox brief queued (`Decision: unify supervised-develop drivers?`,
recommending the narrow yes).

## Soft note (no action)

### S1 — provider/model configured in two places

`dashboard.json` (UI runtime) vs `user_config.toml`/`BACKEND` env
(CLI defaults). Overlapping but different owners. A dashboard
fallback to `user_config` is possible; minor. Note only.

## Cleared suspects (verified NOT redundant)

- `processes.py` / `validation_process.py` /
  `acceptance_processes.py`: share `process_ownership.WindowsJob`;
  distinct roles. Correctly factored, no merge.
- `dashboard_chat.py` vs `coding_chat.py`: layered, 27 boilerplate
  lines. Fine.
- Mail: `owner_mail` shared by dashboard + `loop_notify`; the
  job-email sender is a separate app domain. Fine.
- Acceptance harnesses: research pair shares 8-16 lines; the
  coding-chat pair shares 58 lines but targets differ. Fine.

## Automation candidates (deterministic rails)

- A1 `run-tests.py` per-group summary table — IMPLEMENTED this
  window (commit with this report): each group prints
  `Running <label>: N test modules`, and a closing table names the
  failing group with exit code and seconds. The always-write log
  file was rejected as over-engineering (callers redirect; the
  table says where to look), and streaming output is preserved.
- A2 Triage verdict helper for future audits (12 near-identical
  apply scripts were written this window). Small; deferred to a
  future window, no owner decision needed.
- A3 Inbox decision lifecycle (auto-appended outcome, close,
  archive) — DONE in loop-2.
- R3 Brief pre-flight size estimate — REJECTED (the slice driver
  already fails loud + cheap on over-bound input).
- R4 Sleep-lease auto-renewal — REJECTED (safety-critical; renewals
  stay an explicit observed action).

## Companion suggestion (separate inbox brief)

Legacy `ai_provider` compat shims (`cli`, `external_execution`,
`repo_assistant_args`, `repo_coding_assistant`): deletion was tried
and rejected by the suite gate (`test_cli_basics.py` pins the
contract), so they were restored. Removal + test update proposed in
`Decision: remove legacy ai_provider compat shims?` (recommending
yes — pre-1.0 repo, internal move complete).
