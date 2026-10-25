# Restricted input and future general repository protection

Owner selected A and requested B in plans on 2026-10-25. See ADR-069 for the
decision and the non-sensitive-data tolerance. Neither route cost nor a purchased
credit balance substitutes for input classification and tool-output control.

## A — narrow reviewed input

Use `python -m uv run --no-sync python -m ai_agent.reviewed_task task.txt` from the
workspace to prepare a single UTF-8 task. Review the full file in a local editor. To execute,
pass `--execute --confirm-non-sensitive --approved-sha256 <reviewed digest>`.
The confirmation approves possible retention/training and asserts that the file
contains no keys or genuinely private data. Preparation alone is not consent.

Only those exact task bytes are sent as one USER message. There are no automatic
instructions, tools, history, shell, continuation or fallback. Authentication uses
the existing OPENROUTER_API_KEY environment variable; this command does not load
credential files or copy environment variables into the prompt. Run preparation
without credentials; execution requires the existing adapter credential path.
Avoid putting keys into task text, shell command arguments or review receipts.

The default target is the declared Google Gemma free model. Named `:free` targets
still require fresh adapter price/tool/quota admission. Changing a target is a
caller choice and not authorization for a new live acceptance allowance. Output
and HTTP bounds are explicit. Errors have safe fixed labels, never raw provider
response bodies. Model output is unverified and no proposed tool is executed.

Acceptance: exact wire-input tests; digest mismatch/modified context refusal;
no implicit AGENTS/handoff/session/tool content; credentials stay in authentication;
zero-price/quota/classification guards remain; model tool requests do not execute;
preparation never creates a client. Use synthetic/mock input first. Live route
availability/model quality are separate and cannot be claimed from mocked tests.

## B — general repository protection (planned, not implemented)

Goal: permit useful ordinary coding while preventing genuinely private data and
keys from reaching external model messages. The current workspace/category
permissions do not provide this guarantee. General access is not enabled by A.

Investigate these concrete composition points before proposing implementation:

1. Prompt/context construction: selected files, AGENTS, handoff, skills, nested
   instructions, chat history and retained human decisions. Distinguish required
   instructions from optional data; refusal is preferable to silently dropping
   required instructions or misrepresenting the submitted task.
2. Tool data: reads, searches, diffs, file lists, diagnostics and command stdout/
   stderr, including failed/partial commands. Path exclusion alone does not cover
   a command printing an environment variable or searching excluded directories.
3. Execution: credential exposure through subprocess environment/arguments and
   native/MCP tools. A copied folder is not an OS sandbox when commands can read
   outside it. Evaluate existing capabilities before adding any sandbox/dependency.
4. Continuity: previously safe sessions may contain later sensitive output;
   changing provider must not inherit consent or transfer private continuation.
   Trace saved chat, fallback handoffs and auxiliary/reviewer inputs separately.
5. Classification: determine which exact private datasets/paths are excluded
   (credentials, personal/job-application data, confidential plans/account logs),
   which ordinary non-sensitive repository content is permitted, and how unknown
   content is handled. Do not treat all ignored files as private or all tracked
   files as safe. Secret-pattern detection can supplement a boundary but cannot
   establish absence of arbitrary secrets or semantic private content.

Candidate approaches for owner review after investigation:

- Task/path allowlists with controlled commands and explicit per-task approval:
  easier to audit and fail closed; constrains general workflows and needs careful
  handling of search/shell/history paths.
- Content inspection/redaction across all request composition points: supports
  broader workflows; false negatives can expose data, false positives impede
  coding, and redaction can corrupt required instructions or code.
- A constrained execution environment combined with reviewed egress: stronger
  isolation from unrelated files/credentials; additional platform/dependency and
  maintenance costs need justification and explicit approval.

Technical recommendation for the investigation: reuse existing neutral privacy,
tool-permission and request-composition interfaces; start from real data-flow
counterexamples and a bounded allowlist design, then compare the cost of broader
approaches. No implementation option is selected by this plan. New dependencies,
OS sandboxing, shared approval changes, redaction behavior or public/persisted
contracts retain normal owner decision boundaries.

Independent deterministic preparation can map and test synthetic leakage paths
without any provider request. Proposed live work must use reviewed non-sensitive
payloads and fresh finite bounds; never upload real secrets to test protection.
