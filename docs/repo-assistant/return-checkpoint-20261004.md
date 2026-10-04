# Owner return checkpoint — 2026-10-04

**Implementation INCOMPLETE. Interruption investigation COMPLETE.**

The hosted Codex session recorded `server_overloaded` at 14:02:04.319 UTC
(16:02:04 Europe/Budapest), with the displayed capacity message. This identifies
hosted model availability, rather than a recorded subscription-limit error.
The local scheduler worker continued until 14:05:08 UTC, saved a final handoff
and failed its repair because required input exceeded the local context budget.
It did not keep working for the full five-hour authorization window.

When the owner returned, no scheduler/repo-assistant worker remained and Ollama
reported no loaded models. The idle server's PID, executable and start time matched
the ownership receipt. Cleanup stopped that server and verified no listener on
11434 at 17:00:53 UTC. No other processes were stopped and no sleep was requested.
Local audit receipts remain in `artifacts/cli-contract-window-20261004/`.

## Verified progress

Common inspection tools and checked project-local skills survive forced allowance
fallback through real Copilot. Kiro's production mapping passed a read fixture.
Required repository instructions are retained intact, with overflow refusal.

New opt-in coding continuity stores objectives, explicit decisions and hashed
effect receipts in existing SQLite storage. Native foreground process tools
check completion without an AI call. Restart requires effect reconciliation;
approvals expire, and old PIDs never become live process handles.

The refinement prompt now requests concrete saved-report work or a specific
explanation for making no change, and retains the final response summary. Repair
and refinement now use small marked draft/receipt previews and direct the agent
to its report tools, instead of copying the large tool-free reviewer packet.
Old assistant responses are excerpted; original requirements remain intact. The new
live run failed before proving successful refinement. Reviewer approval alone
does not establish report quality or acceptance success.

Offline validation: 884 passed, seven live tests skipped. Ruff and Pyright pass.
All six foundation recommendations remain accepted under ADR-041.

## Inputs and decisions still needed

### Local IDE connection

The CLI bridge needs an explicitly configured local PyCharm MCP endpoint. Current
host tools are not evidence that an external endpoint is enabled. The official
Python MCP SDK is already approved; it has not been installed or declared while
the concrete transport remains unknown.

Recommendation: use PyCharm's local HTTP-stream connection with its unrestricted
execution option disabled, and project-owned read-only wrappers first. This keeps
endpoint selection explicit and follows the approved temporary IDE-host direction.
Alternative: defer connection activation and continue ordinary filesystem/terminal
tools; semantic IDE parity would remain unavailable to the CLI.

Owner accepted local HTTP-stream activation and read-only wrappers in the next turn.
The actual connection URL/configuration is still missing; activation was not verified.
Connection configuration must omit credentials in chat and repository files.

### Research search configuration

Tavily/Brave were skipped because credentials were absent. The configured SearXNG
search failed upstream. Direct public URL fetching succeeded.

Options:
- Repair or replace the existing SearXNG endpoint: keeps the existing search path,
  but a working endpoint and its operator/privacy properties must be verified.
- Configure an already-supported Tavily or Brave account locally: avoids operating
  a search service, but sends queries to that provider and uses its account limits.
- Use supplied public URLs temporarily: needs no search credentials, but cannot
  establish discovery/search acceptance.

Recommendation: use supplied URLs for the next bounded baseline while diagnosing
the existing SearXNG connection. Select an account-backed provider only if that
operational/privacy trade-off is desired. No provider or global setting was changed.

Owner accepted diagnosing/repairing the existing SearXNG path. An additional
model-free probe returned HTTP 200 JSON with no results and Google suspended
for access denied. An explicit Bing query also returned no results. The instance's
upstream behavior cannot be repaired in this repository; selecting another operator
or account remains a separate privacy/configuration choice if repair proves impossible.

## Added reliability work approved by the owner

The owner also requested handling model overload and context-budget failures.
Temporary overload must remain distinct from exhausted allowance. Error parsing
now recognizes completion events with structured errors, and the CLI explains
capacity failures as hosted availability rather than an account-limit receipt.
The owner subsequently selected automatic overload fallback with a configurable
quality gate. ADR-042 records the implementation: default comparable declared
quality, bounded route attempts, bucket-aware usage fallback and a saved handoff
when no suitable continuation remains. No live calls were made for this change.

Research request sizing now reserves output and framing space and includes tool
schemas in its existing byte estimate. Oversize messages produce a diagnostic with
required bytes and available budget before inference, preserving instructions and
the latest exchange. This is estimated sizing, not verified tokenizer counting;
tool-capable primary exact counts and successful live acceptance remain unfinished.

## Remaining implementation and live checks

Next implement versioned native tool-compatibility evidence and effective input
admission using the existing routing/context contracts; then complete shared
terminal mutation approval across external clients. These directions are approved.
Do not turn unavailable IDE configuration into a reason to stop independent work.

Defer further model runs until another compute window is explicitly available.
Retest context-fit repair/refinement through the research scheduler after the
offline admission fix. Shared mutation, CLI IDE transport and interruption through
external-client fallback also need bounded live acceptance. Generic coding/eval
scheduling and optional capabilities remain outside the approved foundation.
