# ai-workbench skill audit (dashboard idea `f5ff4b70`)

Date: 2026-11-06. Question: do our provider-agnostic agents have
commercial-grade capabilities — compared against agents we integrate
(Codex CLI, verified locally) and the market reference (Claude Code,
official tool docs fetched today)?

Verdict: **core parity, ecosystem gaps**. File read/write/search, shell,
git, delegation, and approval-gated execution match the commercial shape.
The gaps are all outside the inner loop: background execution with
notifications, plan-mode UX, MCP clients, binary/PDF reads, and sharing.

## 1. Our inventory (dumped from registries today)

Inspection profile (chat relay, read-only): 6 tools — read_file, list_dir,
find_files, grep_search, git_status, git_diff.

Coding profile: 15 tools — inspection 6 + create_file, edit_file,
run_command (shell), fetch_url (public pages + receipt), python_runtime,
python_navigate (definitions/references), rename_preview, rename_apply,
delegate_task (one level, narrowed authority + shared budget).

Executor profile (approval-gated runs): 13 tools — inspection 6 +
run_command, python_runtime, python_navigate, rename_preview, stage_file
(staged writes for owner review/apply), request_owner_task (human tasks
to inbox), delegate_task.

Chat-channel tools (dashboard chat only): 3 read-only — get_run_status,
list_pending_inbox (id+type+title, no bodies), read_dashboard_doc (4k cap).

Plus: permission presets (read_only → trusted_local + interactive ASK),
fan-out policy, staged edits with review/apply, run tracking + receipts,
per-task model routing with host allowlist (today), Ollama context tiers
(today). Dashboard adds runs/inbox/documents/ideas/projects over HTTP.

## 2. Claude Code (official tools reference, fetched 2026-11-06)

~45 tools in groups: file (Read/Write/Edit + NotebookEdit), search
(Glob/Grep), shell (Bash/PowerShell), code intelligence (LSP: defs, refs,
type errors), delegation (Agent subagents + teams, SendMessage, Task
family, TodoWrite), planning (EnterPlanMode/ExitPlanMode), review
(ReportFindings), web (WebFetch/WebSearch), MCP (client + resources),
sessions/scheduling (Cron*, RemoteTrigger, ScheduleWakeup), background
(Monitor, TaskOutput/TaskStop), sharing (Artifact, SendUserFile,
ShareOnboardingGuide), misc (AskUserQuestion, Skill, Workflow, Push
notifications, EndConversation, worktrees, hooks).

## 3. Codex CLI (0.166.0, verified via local `--help`)

Command surface, not a tool list (agent tools are internal): non-interactive
exec, review, sandbox (Codex-provided command sandbox), MCP server
management, plugins, session resume/fork/queue/archive/delete, multi-session
app-server daemon, apply (git-apply latest agent diff), doctor
(installation/config/auth/runtime diagnostics), cloud tasks (experimental).

## 4. Gap matrix (ours vs commercial)

| Capability | Us | Claude | Codex | Severity | Notes |
|---|---|---|---|---|---|
| Read/write/edit/search files | yes | yes | yes | — | parity |
| Shell execution | yes (run_command) | yes (Bash/PowerShell) | yes (sandboxed) | low | ours runs unconfined in runs; theirs sandboxed |
| Background exec + wake on output | no | yes (Monitor/Task*) | partial (sessions) | **high** | our long commands block or detach opaquely |
| Plan mode (design → approve → build) | partial (draft-plan API) | yes (Enter/ExitPlanMode) | no (conversational) | medium | ours exists as API, weak as UX |
| Subagents + teams | one level | yes (teams + messaging) | yes (app-server) | medium | ours deliberately shallow; fine for now |
| Task tracking tools | no agent tool (dashboard-side) | yes (Task*/TodoWrite) | no (sessions) | low | dashboard covers it outside the loop |
| Ask-user-question tool | no (inbox instead) | yes | no (chat) | low | inbox is our equivalent; fine |
| Code intelligence (LSP) | python-only navigate | yes (LSP, all langs) | unknown | medium | ours is Python-scoped by design |
| Binary/PDF/notebook reads | no (text only) | yes | unknown | medium | Read handles images/PDF/ipynb there |
| Web search as agent tool | fetch_url only (coding) | yes (WebSearch) | unknown | medium | research loops hand-roll search |
| MCP client | no | yes | yes | medium | would unlock external tools; privacy review needed |
| Review findings structure | receipts (free-form) | yes (ReportFindings) | yes (review cmd) | low | our receipts work; schema would help |
| Sharing/artifacts | dashboard links only | yes (Artifact/URL) | no | low | nice-to-have |
| Notifications (desktop/push) | mail only | yes | no | low | mail covers unattended; desktop would help attended |
| Session resume/fork | chat sessions persist; runs don't resume | yes | yes | medium | our runs are one-shot; resume = re-run |
| Doctor/diagnostics command | no (scattered checks) | n/a | yes (doctor) | medium | matches gap G1; repeatedly requested |
| Cron/scheduling in-agent | no (OS scheduled tasks) | yes (session cron) | no | low | OS tasks cover it; different layer |

## 5. Recommendations (ranked)

1. **Background run_command + completion surfacing** (P1). The most
   visible capability gap: every long operation today blocks a turn or
   detaches opaquely. Shape: run_command gains background start + output
   polling/status tool; dashboard shows running commands. Effort: medium.
2. **Binary reads** (P2). Read path for PDF/images/notebooks (at least
   text extraction). Unblocks research + document workflows. Effort:
   small-medium (pypdf/PIL are small deps, or CLI fallbacks).
3. **In-agent web search** (P2). Promote search to a first-class agent
   tool (we already hold Brave/Tavily keys) instead of hand-rolled
   research code. Effort: small (adapter exists in research paths).
4. **Doctor command** (P2, = gap G1). Single health surface for
   services/tasks/routes/credentials. Effort: medium; mostly assembly.
5. **MCP client** (P3). High leverage, but needs a privacy Architecture
   Decision (external data routing) first — queue the ADR, not the code.
6. **Session resume for runs** (P3). Re-run exists; true resume needs
   persisted loop state. Defer until a run actually needs mid-run resume.
7. Everything else (artifacts, desktop notify, plan-mode UX polish):
   defer; no commercial dealbreaker observed.

Non-gaps worth stating: staged writes + owner review/apply, per-task model
routing, and the inbox human-task loop are *ahead* of the commercial
baseline for supervised solo-founder use — do not trade them for parity.

## 6. Method + confidence

Our side: executed registry dumps (exact). Claude side: official tools
reference fetched 2026-11-06 (exact). Codex side: local CLI `--help`
(commands exact; internal agent toolset inferred from product behavior —
medium confidence, flagged where it matters). Severity = commercial
usefulness × frequency, solo-founder lens. Findings only; no code changed
(this audit answers dashboard idea `f5ff4b70`, which stays `reviewing`
for owner triage).
