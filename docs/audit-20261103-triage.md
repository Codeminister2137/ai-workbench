# Frontier audit triage — 2026-11-03

Full-repo audit (option B) via `muse-spark-1.3`: 16 chunks, 504 files,
~1.33M input tokens. Cost $2.19 of the $25 allowance `audit-meta-20261103`
(19 calls, 0 errors). Raw chunk responses: ignored `.tmp/audit-b/` (scratch).

Verdict scale: FIXED / TEST GAP CLOSED / FALSE POSITIVE / INTENDED /
DOWNGRADED / BACKLOG / REAL — POST-HACKATHON / UNREVIEWED.

Reviewed tonight: all remote-operator HIGHs + judge cap + redact + sandbox;
workbench CRITICALs, Gmail, repo_actions, day_cycle. Everything else needs
verification before action — several audit claims were already proven wrong
(smoke tokens, expire design, cross-subject product, plan-files, Gmail).

## ai-workbench/0

- [HIGH] Public Modal endpoint depends solely on in-container API key — `deploy/modal/qwen25-coder-7b/modal_app.py` → **UNREVIEWED**
- [MEDIUM] Supervisor token absent means allow-all — `apps/workbench_dashboard/dashboard_stores.py` → **UNREVIEWED**
- [MEDIUM] Transcript list crashes on concurrent delete/unreadable file — `apps/workbench_dashboard/dashboard_stores.py` → **UNREVIEWED**
- [MEDIUM] Chat factory exception bypasses failure envelope — `apps/workbench_dashboard/dashboard_chat.py` → **UNREVIEWED**
- [MEDIUM] Approve path leaks raw OSError on missing CV — `apps/job_search/job-email/approval.py` → **UNREVIEWED**
- [MEDIUM] Unknown chat roles silently dropped — `apps/ai_council/agent.py` → **UNREVIEWED**
- [MEDIUM] Blocking council ask aborts on first member failure — `apps/ai_council/council.py` → **UNREVIEWED**
- [MEDIUM] Chat session id taken from raw URL slice — `apps/workbench_dashboard/dashboard_web_app.py` → **UNREVIEWED**
- [MEDIUM] Sent-ledger append without lock or fsync — `apps/job_search/job-email/outreach_cli.py` → **UNREVIEWED**
- [LOW] vLLM shutdown never waits/kills — `deploy/modal/qwen25-coder-7b/modal_app.py` → **UNREVIEWED**
- [LOW] 48-bit application id truncation — `apps/job_search/job-email/preparation.py` → **UNREVIEWED**
- [LOW] New provider client per member per turn — `apps/ai_council/council.py` → **UNREVIEWED**
- [LOW] Decision dedupe is exact case-sensitive title match — `apps/workbench_dashboard/plan_publisher.py` → **UNREVIEWED**

## ai-workbench/1

- [HIGH] MCP stdio server crashes on tool exception — `packages/ai_agent/src/ai_agent/mcp_server.py` → **UNREVIEWED**
- [HIGH] Delegated child uses permissive permissions — `packages/ai_agent/src/ai_agent/mcp_server.py` → **UNREVIEWED**
- [HIGH] Delegated CLI scope also escalates to permissive — `packages/ai_agent/src/ai_agent/repo_coding_assistant.py` → **UNREVIEWED**
- [MEDIUM] Fallback handoff writes files outside permission system — `packages/ai_agent/src/ai_agent/repo_coding_assistant.py` → **UNREVIEWED**
- [MEDIUM] Process handle map accessed without lock — `packages/ai_agent/src/ai_agent/processes.py` → **UNREVIEWED**
- [MEDIUM] Codex login subprocess can hang forever — `packages/ai_agent/src/ai_agent/repo_coding_assistant.py` → **UNREVIEWED**
- [MEDIUM] Unbounded repair loop when max-cycles=-1 and no deadline — `packages/ai_agent/src/ai_agent/repair_workflow.py` → **UNREVIEWED**
- [MEDIUM] Research source retain crashes on malformed receipt — `packages/ai_agent/src/ai_agent/research_evidence.py` → **UNREVIEWED**
- [MEDIUM] IDE tool cannot run inside existing event loop — `packages/ai_agent/src/ai_agent/ide_bridge.py` → **UNREVIEWED**
- [MEDIUM] Provider model-list probe can SSRF to catalog URL — `packages/ai_agent/src/ai_agent/repo_coding_assistant.py` → **UNREVIEWED**
- [MEDIUM] Delegated error string leaks internals to model — `packages/ai_agent/src/ai_agent/repo_coding_assistant.py` → **UNREVIEWED**
- [LOW] Negative context budgets not rejected — `packages/ai_agent/src/ai_agent/repo_assistant_args.py` → **UNREVIEWED**
- [LOW] Env passthrough skips argv-style validation — `packages/ai_agent/src/ai_agent/processes.py` → **UNREVIEWED**
- [LOW] Review-source allocation recomputes UTF-8 size per share — `packages/ai_agent/src/ai_agent/research_evidence.py` → **UNREVIEWED**

## ai-workbench/10

- [MEDIUM] Loopback handler enforces auth with `assert` — `tests/test_hosted_delegation_acceptance.py` → **UNREVIEWED**
- [LOW] Global `sys.path` mutation without restore — `tests/test_mail_digest.py` → **UNREVIEWED**
- [LOW] Global `sys.modules` pollution by script loader — `tests/test_l3_ladder.py` → **UNREVIEWED**
- [HIGH] Bounded join then hard liveness assert is flaky — `tests/test_hosted_delegation_acceptance.py` → **UNREVIEWED**
- [MEDIUM] Incorrect POSIX shell quoting of interpreter path — `tests/test_hosted_delegation_acceptance.py` → **UNREVIEWED**
- [MEDIUM] Cross-test module import creates order dependency — `tests/test_measured_prefix_admission.py` → **UNREVIEWED**
- [MEDIUM] Whole `time` module replaced by sleep-only stub — `tests/test_loop_notify.py` → **UNREVIEWED**
- [MEDIUM] Stale-bytecode test assumes nanosecond mtime fidelity — `tests/test_opencode_go_coding_chat_acceptance.py` → **UNREVIEWED**
- [MEDIUM] Double shutdown path for test HTTP server — `tests/test_hosted_delegation_acceptance.py` → **UNREVIEWED**
- [LOW] Deadlines asserted with wall-clock bounds — `tests/test_kiro_usage.py` → **UNREVIEWED**
- [LOW] Unverified version path leaks request expectation — `tests/test_kiro_usage.py` → **UNREVIEWED**
- [MEDIUM] Duplicated `Response`/`FakeHttpResponse` harnesses — `tests/test_go_source_info.py` → **UNREVIEWED**
- [LOW] Repeated `spec_from_file_location` script loading — `tests/test_loop_notify.py` → **UNREVIEWED**
- [LOW] Hard-coded heartbeat sleep tight-loop in SDK test — `tests/test_ide_bridge_sdk.py` → **UNREVIEWED**

## ai-workbench/11

- [MEDIUM] Predictable PID tmp file allows symlink hijack — `tests/test_pid_publication.py` → **UNREVIEWED**
- [LOW] Unbounded PID file read — `tests/test_pid_publication.py` → **UNREVIEWED**
- [LOW] Dynamic PowerShell code execution via Invoke-Expression — `tests/test_research_runner.py` → **UNREVIEWED**
- [HIGH] cp1252 stdout test crashes on emoji print — `tests/test_requesty_free_models.py` → **UNREVIEWED**
- [MEDIUM] Hardlink test lacks Windows/privilege guard — `tests/test_research_tools.py` → **UNREVIEWED**
- [MEDIUM] Descendant-kill assertion is timing-flaky — `tests/test_research_runner.py` → **UNREVIEWED**
- [MEDIUM] Relative catalog path depends on CWD — `tests/test_repair_progress.py` → **UNREVIEWED**
- [MEDIUM] Stale PID ValueError escapes FileNotFoundError contract — `tests/test_pid_publication.py` → **UNREVIEWED**
- [LOW] Broad exception swallow hides publication races — `tests/test_pid_publication.py` → **UNREVIEWED**
- [LOW] Test pollutes shared parent temp dir — `tests/test_operator_bridge.py` → **UNREVIEWED**
- [LOW] Duplicated candidate/entry builders across suites — `tests/test_orchestrator_recommender.py` → **UNREVIEWED**
- [LOW] Duplicated pinned-HTTP fake connection harness — `tests/test_research_search.py` → **UNREVIEWED**
- [LOW] Fixed sleeps instead of clock injection — `tests/test_pid_publication.py` → **UNREVIEWED**

## ai-workbench/12

- [MEDIUM] Sys.path insert + plain import enables module hijack — `tests/test_sender_unify.py` → **UNREVIEWED**
- [MEDIUM] PowerShell commands built by single-quote interpolation of paths — `tests/test_workstation_sleep.py` → **UNREVIEWED**
- [LOW] Test executes product scripts at import time — `tests/test_test_suites.py` → **UNREVIEWED**
- [LOW] Dynamic `python -c` worker built by f-string — `tests/test_task_scheduler.py` → **UNREVIEWED**
- [MEDIUM] Resource bound guard only covers `rb` mode — `tests/test_semantic_refactor.py` → **UNREVIEWED**
- [MEDIUM] Unbounded busy-wait for `release` sentinel — `tests/test_shell_process_ownership.py` → **UNREVIEWED**
- [MEDIUM] Receipt poll swallows `PermissionError` — `tests/test_workstation_sleep.py` → **UNREVIEWED**
- [LOW] Non-atomic consumer receipt write — `tests/test_sender_unify.py` → **UNREVIEWED**
- [LOW] `/proc` stat parse assumes `) `-delimited format — `tests/test_validation_process_ownership.py` → **UNREVIEWED**
- [LOW] Duplicated suspend-shim string replacement — `tests/test_workstation_sleep.py` → **UNREVIEWED**
- [LOW] Hard-coded timing assertions invite flakes — `tests/test_shell_process_ownership.py` → **UNREVIEWED**
- [LOW] Inline TOML catalogs duplicated across suites — `tests/test_shared_coding_fallback.py` → **UNREVIEWED**

## ai-workbench/2

- [HIGH] Arbitrary shell execution via model-controlled command — `packages/ai_agent/src/ai_agent/tools/shell.py` → **UNREVIEWED**
- [HIGH] Full parent environment inherited by model-chosen subprocess — `packages/ai_agent/src/ai_agent/tools/base.py` → **UNREVIEWED**
- [MEDIUM] Untrusted skill file becomes trusted model instructions — `packages/ai_agent/src/ai_agent/skills.py` → **UNREVIEWED**
- [MEDIUM] Candidate-controlled text concatenated into reviewer prompts — `packages/ai_agent/src/ai_agent/scrutiny_workflow.py` → **UNREVIEWED**
- [MEDIUM] Catalog base_url trusted without validation enables SSRF — `packages/ai_provider/examples/orchestrator_execution_target.py` → **UNREVIEWED**
- [LOW] Credential-path blocklist misses common secret filenames — `packages/ai_agent/src/ai_agent/tools/credential_paths.py` → **UNREVIEWED**
- [HIGH] Rename apply can half-succeed with no rollback — `packages/ai_agent/src/ai_agent/tools/refactor.py` → **UNREVIEWED**
- [MEDIUM] Model IDs lowercased in derived route_id — `packages/ai_orchestrator/src/ai_orchestrator/catalog.py` → **UNREVIEWED**
- [MEDIUM] Unbounded last-message file read after Codex run — `packages/ai_orchestrator/examples/codex_cli_executor.py` → **UNREVIEWED**
- [LOW] Git failure returned as data tuple masks errors — `packages/ai_agent/src/ai_agent/run_tracking.py` → **UNREVIEWED**
- [LOW] Repeated workspace resolve + file reads in scrutiny loop — `packages/ai_agent/src/ai_agent/scrutiny_workflow.py` → **UNREVIEWED**

## ai-workbench/3

- [HIGH] Unbounded provider response reads allow OOM — `packages/ai_provider/src/ai_provider/adapters/openai_compatible.py` → **UNREVIEWED**
- [MEDIUM] Codex MCP server_name TOML injection + unconstrained write — `packages/ai_provider/src/ai_provider/codex_mcp.py` → **UNREVIEWED**
- [MEDIUM] netstat path from attacker-influenced environment — `packages/ai_provider/src/ai_provider/acceptance_processes.py` → **UNREVIEWED**
- [MEDIUM] Closeout log injection via unsanitized route ids and CR — `packages/ai_provider/src/ai_provider/closeout.py` → **UNREVIEWED**
- [MEDIUM] Stored chat role crash on invalid value — `packages/ai_provider/src/ai_provider/chat_transcripts.py` → **UNREVIEWED**
- [MEDIUM] Coding-session process observer assumes keys/types — `packages/ai_provider/src/ai_provider/coding_sessions.py` → **UNREVIEWED**
- [MEDIUM] Missing stream-chunk size bound in all adapters — `packages/ai_provider/src/ai_provider/adapters/ollama.py` → **UNREVIEWED**
- [LOW] Negative/limitless chat session listing — `packages/ai_provider/src/ai_provider/chat_transcripts.py` → **UNREVIEWED**
- [LOW] Rolling-summary metadata stored but dropped from return — `packages/ai_provider/src/ai_provider/chat_transcripts.py` → **UNREVIEWED**
- [LOW] Prior snapshot read has no byte bound — `packages/ai_provider/src/ai_provider/capability_bands.py` → **UNREVIEWED**
- [LOW] Duplicated Ollama startup branches — `packages/ai_provider/src/ai_provider/coding_assist.py` → **UNREVIEWED**

## ai-workbench/4

- [CRITICAL] Unsafe exec of model output with escapable bare namespace — `packages/ai_provider/src/ai_provider/route_eval.py` → **REAL — POST-HACKATHON** (in-process exec of model text; builtins-stripped but dunder-escape possible; grade in subprocess sandbox)
- [HIGH] Model-proposed shell execution via /bin/sh -c — `packages/ai_provider/src/ai_provider/repo_actions.py` → **DOWNGRADED** (only caller passes interactive authorizer; library default None is a footgun — consider required authorizer)
- [HIGH] Full parent env (secrets) inherited by external agent child — `packages/ai_provider/src/ai_provider/foreground_tools.py` → **UNREVIEWED**
- [MEDIUM] Arbitrary base_url fetched without loopback/redirect guard — `packages/ai_provider/src/ai_provider/ollama_models.py` → **UNREVIEWED**
- [MEDIUM] User prompt preview persisted to SQLite without redaction — `packages/ai_provider/src/ai_provider/orchestrated_runs.py` → **UNREVIEWED**
- [MEDIUM] Env-controlled executable used as subprocess without validation — `packages/ai_provider/src/ai_provider/external_agents.py` → **UNREVIEWED**
- [HIGH] Asserts used for runtime control flow — `packages/ai_provider/src/ai_provider/fallback_diagnostics.py` → **UNREVIEWED**
- [MEDIUM] Unbounded workspace file hashing enables DoS/OOM — `packages/ai_provider/src/ai_provider/repair_state.py` → **UNREVIEWED**
- [MEDIUM] Pinned Gemini chunk filename makes verification brittle — `packages/ai_provider/src/ai_provider/gemini_cli.py` → **UNREVIEWED**
- [MEDIUM] Exclusive settings create has no exists-handling — `packages/ai_provider/src/ai_provider/gemini_cli.py` → **UNREVIEWED**
- [MEDIUM] Unvalidated timeout flows into min()/urlopen — `packages/ai_provider/src/ai_provider/native_admission.py` → **UNREVIEWED**
- [MEDIUM] Silent diagnostic swallow hides fallback mode — `packages/ai_provider/src/ai_provider/fallback_context.py` → **UNREVIEWED**
- [MEDIUM] Kiro/An antigravity headless denial masked as success elsewhere — `packages/ai_provider/src/ai_provider/external_agents.py` → **UNREVIEWED**
- [LOW] TOCTOU on Kiro/Gemini workspace check — `packages/ai_provider/src/ai_provider/external_agents.py` → **UNREVIEWED**
- [LOW] Blocking input() for outside-repo approval — `packages/ai_provider/src/ai_provider/repo_actions.py` → **UNREVIEWED**
- [LOW] History compaction can still throw after preserving required data — `packages/ai_provider/src/ai_provider/research_execution.py` → **UNREVIEWED**
- [MEDIUM] sys.modules self-replacement hides implementation — `packages/ai_provider/src/ai_provider/external_execution.py` → **UNREVIEWED**
- [LOW] Substring haystack over-classifies tool/file events — `packages/ai_provider/src/ai_provider/external_agents.py` → **UNREVIEWED**
- [LOW] Per-message 256 framing double-counts schemas — `packages/ai_provider/src/ai_provider/research_review.py` → **UNREVIEWED**

## ai-workbench/5

- [MEDIUM] Inbox run_id path traversal read — `patches/operator-notify-fix/src/remote_operator/supervisor_inbox.py` → **UNREVIEWED**
- [MEDIUM] Cost policy configured but never applied — `packages/ai_provider/src/ai_provider/user_config.py` → **UNREVIEWED**
- [MEDIUM] Transcript logs full prompts verbatim — `packages/ai_provider/src/ai_provider/transcripts.py` → **UNREVIEWED**
- [MEDIUM] .env permission never checked — `packages/ai_provider/src/ai_provider/secrets.py` → **UNREVIEWED**
- [MEDIUM] probe_route allows arbitrary URL fetch — `packages/ai_provider/src/ai_provider/route_probe.py` → **UNREVIEWED**
- [MEDIUM] Shared profile writes literal "None" session id — `packages/ai_provider/src/ai_provider/shared_client_tools.py` → **UNREVIEWED**
- [MEDIUM] Negative/NaN schedule accepted at plan time — `packages/ai_provider/src/ai_provider/task_scheduler.py` → **UNREVIEWED**
- [LOW] Research scrutiny prompt unbounded — `packages/ai_provider/src/ai_provider/scrutiny.py` → **UNREVIEWED**
- [LOW] SWE-bench source_url unvalidated fetch — `packages/ai_provider/src/ai_provider/swe_bench_scores.py` → **UNREVIEWED**
- [LOW] Workspace join bypass if CONFIG_PATH absolute — `packages/ai_provider/src/ai_provider/shared_client_tools.py` → **UNREVIEWED**
- [LOW] Drain crash on corrupt attempts value — `patches/operator-notify-fix/src/remote_operator/supervisor_runner.py` → **UNREVIEWED**
- [LOW] Unbounded TOML config read — `packages/ai_provider/src/ai_provider/user_config.py` → **UNREVIEWED**
- [LOW] dotenv export prefix silently dropped — `packages/ai_provider/src/ai_provider/secrets.py` → **UNREVIEWED**
- [LOW] Display key whitespace not normalized — `packages/ai_provider/src/ai_provider/swe_bench_scores.py` → **UNREVIEWED**

## ai-workbench/6

- [CRITICAL] Arbitrary local file read exfiltrated to Baseten — `scripts/plan-with-supervisor.py` → **FALSE POSITIVE** (operator CLI reading operator-named files is the tool function; no boundary crossed)
- [HIGH] Snapshot command-line replay gives local RCE — `scripts/day_cycle.py` → **REAL — POST-HACKATHON** (artifacts file-write replays on open (Windows Popen-str); store argv + allowlist, echo cmdline; POSIX path broken anyway)
- [HIGH] All provider keys exposed to every agent subprocess — `scripts/alternate-agent-acceptance.py` → **UNREVIEWED**
- [HIGH] Private Gmail content sent to external Meta model — `scripts/mail_digest.py` → **INTENDED** (owner tool, owner key, documented no-training route; subject+snippet only)
- [MEDIUM] Unencoded server-controlled IDs in fetch paths — `patches/operator-ui-guided/app.js` → **UNREVIEWED**
- [MEDIUM] Owner ping leaks host IP to external service by default — `scripts/loop_notify.py` → **UNREVIEWED**
- [HIGH] Validator allowance keys accessed without validation — `scripts/meta-supervised-develop.py` → **UNREVIEWED**
- [MEDIUM] Security gates use `assert`, stripped under `python -O` — `scripts/fallback-acceptance.py` → **UNREVIEWED**
- [MEDIUM] Unbounded mailbox/body reads allow DoS/OOM — `scripts/mail_digest.py` → **UNREVIEWED**
- [MEDIUM] `.env` read crashes when file missing — `scripts/alternate-agent-acceptance.py` → **UNREVIEWED**
- [MEDIUM] Controller launch parses JSON without handling — `scripts/bounded-acceptance-controller.py` → **UNREVIEWED**
- [MEDIUM] Duplicated model-resolution branches drift — `scripts/baseten-supervised-develop.py` → **UNREVIEWED**
- [LOW] PowerShell port-parse fragile to locale/whitespace — `scripts/day_cycle.py` → **UNREVIEWED**
- [LOW] `save_json` temp suffix collides on concurrent runs — `scripts/research-review-evaluation.py` → **UNREVIEWED**

## ai-workbench/7

- [HIGH] Worktree-joined model file write without traversal check — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [HIGH] External exfiltration via unvalidated `worktree/files` join — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [HIGH] Objective-id used as filesystem path without sanitization — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [HIGH] Destructive git wipe on unvalidated queue path — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [MEDIUM] PATH fallback for linter binary — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [MEDIUM] Unbounded WOL flooder to arbitrary target — `scripts/wake_on_lan.py` → **UNREVIEWED**
- [HIGH] `except BaseException` swallows cancel/exit — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [HIGH] Malformed queue crashes error handler — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [MEDIUM] Missing size/symlink guard on workbench file ingest — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [MEDIUM] Hardcoded Windows interpreters + username leak — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [MEDIUM] Missing CLI bounds in WOL and report validator — `scripts/wake_on_lan.py` → **UNREVIEWED**
- [MEDIUM] Receipt/phase files assumed present and well-formed — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [LOW] Insecure `.env` parsing for event credential — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [LOW] Blocking `Popen` receipt wait can mask closeout failure — `scripts/unattended-development-loop.py` → **UNREVIEWED**
- [LOW] Stream research-file hash instead of `read_bytes` — `scripts/validate_research_report.py` → **UNREVIEWED**

## ai-workbench/8

- [HIGH] Malicious validator escape only verified on Windows — `tests/test_acceptance_jobs.py` → **UNREVIEWED**
- [HIGH] Owned-child cleanup has no Linux coverage — `tests/test_acceptance_jobs.py` → **UNREVIEWED**
- [MEDIUM] Test SSRF/size guards use `assert` (stripped under `-O`) — `tests/repo_assistant/test_protocol_continuity.py` → **UNREVIEWED**
- [MEDIUM] Git helpers run without timeout — `tests/test_ai_agent_git_tools.py` → **UNREVIEWED**
- [MEDIUM] Junction creation via PowerShell has no timeout — `tests/test_ai_agent_boundaries.py` → **UNREVIEWED**
- [MEDIUM] Fixed 2-item input iterator masks over-prompting — `tests/repo_assistant/test_protocol_continuity.py` → **UNREVIEWED**
- [MEDIUM] Auxiliary startup stub ignores `base_url` — `tests/repo_assistant/test_orchestration.py` → **UNREVIEWED**
- [LOW] Duplicate create_file byte-count tests — `tests/test_ai_agent_tools.py` → **UNREVIEWED**
- [LOW] 30-60s fixture sleeps slow and flake — `tests/repo_assistant/test_protocol_continuity.py` → **UNREVIEWED**

## ai-workbench/9

- [HIGH] Test helper executes workspace-controlled file via `exec` — `tests/test_execution_fallback.py` → **UNREVIEWED**
- [MEDIUM] Full host environ forwarded to stdio proxy child — `tests/test_foreground_http.py` → **UNREVIEWED**
- [MEDIUM] Eval harness suggests in-process `exec` of model output — `tests/test_ai_provider_route_eval.py` → **UNREVIEWED**
- [LOW] Redirect test proves credential-bearing retry would leak prompt — `tests/test_ai_provider_transport.py` → **UNREVIEWED**
- [MEDIUM] Receipt poll has no corrupt/missing-dir contract — `tests/test_baseten_receipts.py` → **UNREVIEWED**
- [MEDIUM] `valid_source` only tested against naive payloads — `tests/test_fallback_acceptance.py` → **UNREVIEWED**
- [MEDIUM] Exhausted-deadline / allowance-observer races untested for partial writes — `tests/test_execution_fallback.py` → **UNREVIEWED**
- [LOW] Dotenv parser leaves `export` / inline-comment behavior undefined — `tests/test_ai_provider_secrets.py` → **UNREVIEWED**
- [LOW] Band validator bool edge only half-covered — `tests/test_capability_bands.py` → **UNREVIEWED**
- [LOW] Pricing-read assertion allows unbounded extra fetches — `tests/test_free_provider_fallback.py` → **UNREVIEWED**
- [LOW] SQLite connection-leak test is process-global — `tests/test_chat_transcripts.py` → **UNREVIEWED**
- [LOW] Duplicated `Response(BytesIO)` / `transport` shims across suites — `tests/test_ai_provider_route_probe.py` → **UNREVIEWED**
- [LOW] Repeated catalog-path and `ScriptedClient` boilerplate — `tests/test_execution_fallback.py` → **UNREVIEWED**
- [LOW] Synthetic `time.sleep(30)` children make suite timing-fragile — `tests/test_codex_usage.py` → **UNREVIEWED**

## remote-operator/0

- [MEDIUM] Browser smoke writes live token to disk config — `scripts/browser_smoke.py` → **FALSE POSITIVE** (synthetic token_urlsafe + finally-unlink)
- [MEDIUM] Hosted smoke writes access code to disk config — `scripts/hosted_browser_smoke.py` → **FALSE POSITIVE** (synthetic token_urlsafe + finally-unlink)
- [MEDIUM] Judge USD cap has no upper bound — `src/remote_operator/judge_grants.py` → **FIXED** (cap 100 server+UI+test (batch1))
- [HIGH] Duplicate `id="preview"` leaves one button dead — `src/remote_operator/index.html` → **FIXED** (removed dead dup; page-ids-unique test (batch1, 8e825f5))
- [HIGH] Expire inside open transaction uses second connection — `src/remote_operator/external_actions.py` → **FALSE POSITIVE** (separate connection is comment-documented (rolls back otherwise); no lock held on SELECT)
- [MEDIUM] `request()` decode failure escapes as exception — `src/remote_operator/modal_runner.py` → **UNREVIEWED**
- [MEDIUM] `_redact` with empty key corrupts every string — `src/remote_operator/meta.py` → **FIXED** (empty-key guard meta+baseten+tests (batch1); unreachable in current flows (latent))
- [MEDIUM] Same empty-key redact in Baseten path — `src/remote_operator/baseten.py` → **FIXED** (see above (batch1))
- [MEDIUM] `schedule_sleep` claims scheduled on non-Windows — `src/remote_operator/power.py` → **UNREVIEWED**
- [MEDIUM] Unbounded judge signup fills SQLite — `src/remote_operator/judge_accounts.py` → **UNREVIEWED**
- [LOW] Debug `print` in host loop — `src/remote_operator/development.py` → **UNREVIEWED**
- [LOW] Expiry error leaks token-hash prefix — `src/remote_operator/hosted.py` → **UNREVIEWED**
- [LOW] `send_owner_mail` lets non-transport errors escape — `src/remote_operator/notify.py` → **UNREVIEWED**
- [LOW] Narrow `cancel_sleep` leaves stale scheduled receipt — `src/remote_operator/power.py` → **UNREVIEWED**
- [LOW] Env parser strips quotes asymmetrically — `scripts/check_submission_eligibility.py` → **UNREVIEWED**

## remote-operator/1

- [HIGH] Host allowlist bypass via spoofable Host header — `src/remote_operator/web.py` → **BACKLOG** (true in theory; unreachable (bind 127.0.0.1, Modal routes by Host); client.host hardening needs test rework (TestClient host))
- [MEDIUM] Session cookie Secure conditional on public_origin — `src/remote_operator/web.py` → **UNREVIEWED**
- [MEDIUM] Sandbox file materialization follows symlinks as root — `src/remote_operator/sandbox_bootstrap.py` → **UNREVIEWED**
- [MEDIUM] Allowance ledger allows non-finite USD to bypass cap — `src/remote_operator/store.py` → **UNREVIEWED**
- [HIGH] Sandbox request assumes string payload without validation — `src/remote_operator/sandbox_bootstrap.py` → **FIXED** (payload validated before writes + test (batch1))
- [HIGH] Run-job files lack durability hook used by task store — `src/remote_operator/supervisor_runner.py` → **UNREVIEWED**
- [MEDIUM] Owner-replies lookup capped at 50 threads creates duplicates — `src/remote_operator/supervisor.py` → **UNREVIEWED**
- [MEDIUM] SQLite busy errors escape allowance/cancel transactions — `src/remote_operator/store.py` → **UNREVIEWED**
- [MEDIUM] Inbox terminal-run mapping trusts mutable job file over event — `src/remote_operator/supervisor_inbox.py` → **UNREVIEWED**
- [LOW] Window loader hides corruption as idle — `src/remote_operator/window_status.py` → **UNREVIEWED**
- [LOW] Inbox does N+1 store reads and full run-dir scan per item — `src/remote_operator/supervisor_inbox.py` → **UNREVIEWED**
- [LOW] Planning-thread listing fetches full records to filter — `src/remote_operator/supervisor.py` → **UNREVIEWED**

## remote-operator/2

- [MEDIUM] `cmd /c mklink` test helper allows shell metachar injection — `tests/test_sessions.py` → **UNREVIEWED**
- [LOW] Predictable owner bearer token pattern reused across suites — `tests/test_web.py` → **UNREVIEWED**
- [LOW] Shared hardcoded demo access code across hosted suites — `tests/test_hosted_drain.py` → **UNREVIEWED**
- [LOW] Synthetic secrets passed to Docker via `-e` env list — `tests/test_modal_runner.py` → **UNREVIEWED**
- [HIGH] Cross-subject isolation only checks `runs`, not direct `tasks/{id}` — `tests/test_hosted_drain.py` → **TEST GAP CLOSED** (product already scoped per-subject; tasks/id isolation test added (batch1))
- [MEDIUM] Login throttle pins trigger but not reset/expiry or success-after-lock — `tests/test_judges.py` → **UNREVIEWED**
- [MEDIUM] Busy/drain race covers single lock, not parallel double-claim — `tests/test_supervisor_runner.py` → **UNREVIEWED**
- [MEDIUM] Drain-worker survival test relies on fixed sleep — `tests/test_supervisor_drain_worker.py` → **UNREVIEWED**
- [MEDIUM] Audio body-cap exemption only proves 413 on non-multipart — `tests/test_stt.py` → **UNREVIEWED**
- [LOW] 30-day self-grant expiry only tested at -31 days — `tests/test_judges.py` → **UNREVIEWED**
- [LOW] Malformed job file covers single `not json{` case — `tests/test_supervisor_runner.py` → **UNREVIEWED**
- [LOW] STT concurrency test reaches into private semaphore — `tests/test_stt.py` → **UNREVIEWED**
- [MEDIUM] Duplicated `Validator`/`AskOnceModel`/`grant()` doubles in every file — `tests/test_hosted_drain.py` → **UNREVIEWED**
- [LOW] Duplicated `_operator` / `_planned` / `_serve` HTTP scaffolding — `tests/test_notify_fix.py` → **UNREVIEWED**
- [LOW] Deadline polling loops duplicated with magic intervals — `tests/test_hosted_drain.py` → **UNREVIEWED**

## Verdict counts

- BACKLOG: 1
- DOWNGRADED: 1
- FALSE POSITIVE: 4
- FIXED: 5
- INTENDED: 1
- REAL — POST-HACKATHON: 2
- TEST GAP CLOSED: 1
- UNREVIEWED: 200

## Appendix: frontend-audit leftovers verified 2026-11-03 evening

The focused frontend audit (24 findings, `muse-spark-1.3`, $0.08) had 20
fixes merged to sibling main as `5c822ce`. The remaining findings were
re-verified against current sibling code this evening; two were fixed on
sibling branch `fix/frontend-copy-20261103` (`bc43bdc`, full suite 576
passed / 9 skipped / 265 subtests, harness prefix-checked against pre-fix
sources, merge queued for the 20:00 owner review under the UI freeze).

FIXED tonight (`bc43bdc`, queued for merge):

- [HIGH] Meta vs Baseten vs key language — REAL. `keyNote()` said
  "charged to your own Meta account" even in Baseten mode, where the
  server-side event key funds inference. Now mode-aware (Baseten /
  Meta / no-route wordings), covered by `tests/js_actions.cjs`.
- [HIGH] Run-mode scope vs supervision scope — REAL. Scopes lived only
  in toggletips, and the run tip ("next task you create") was imprecise:
  `runMode` is read only at plan approval. Labels now read "Run mode
  (next plan)" / "Supervision (all runs)"; tip corrected to "next plan
  you approve". Covered by `tests/js_actions.cjs`.

Already fixed in current code (audit staleness; no action):

- [HIGH] Approval-window wordings — term unified ("Review windows",
  "Review window: ~N min left", "approve within ~N min").
- [MEDIUM] Inject checkbox vs Resume — Resume title already scopes the
  checkbox to Create-and-run; Resume sends `inject_failure: false`.
- [LOW] Build chip ellipsis — shows "build ?" with an explanatory title.
- [MEDIUM] powerArm confirm survives disconnect — token handler resets
  `powerArmed` and the label (part of the 20-fix batch).
- [MEDIUM] Sticky nav + 100% buttons — media query already excludes
  `#viewNav button` (`width:auto`).
- [LOW] Sticky nav hides anchors — sections carry `scroll-margin-top`.
- [MEDIUM] Inbox tooltip jargon — plain text now ("Updates with each
  refresh; ...").
- [LOW] Unread badge SR announcement — badge span has `role="status"`
  + `aria-live="polite"`.

Deferred / no change:

- [HIGH] Touch targets 24px — REAL but visual: `button{min-height:24px}`
  is below the 44px guidance; raising it globally risks the tuned
  phone layout the night before submit. Needs owner eyes; queued.
- [MEDIUM] Pill/status contrast — FALSE POSITIVE by measurement: WCAG
  ratios 5.46-12.82 on both page and section backgrounds (AA needs 4.5).
- [MEDIUM] 3-step vs 4-step counts — acceptable as-is: the quick start
  and the setup wizard are different components. Noted for 20:00.
