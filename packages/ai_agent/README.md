# ai-agent

Agentic tool execution loop, tool registry, permission policies, and multi-turn coding session management built on top of `ai_orchestrator` and `ai_provider`.

## Features
- **Provider-Neutral Tool Registry**: Define tools with strict JSON schemas and run them across local and hosted models.
- **Built-in Coding Tools**: Safe file reading, slice editing, creation, directory listing, regex/grep search, and shell execution.
- **Permission & Safety Control**: Configurable approval policies for read vs. write vs. command execution, with workspace boundary enforcement.
- **Authorization Boundary**: Secret-free contracts for external service authorization state, read/write grants, credential locations, and reusable diagnostics.
- **Agent Loop**: Provider-neutral multi-turn tool-calling cycle with permission enforcement, tool-result messages, and iteration limits.
- **Public Research Tools**: Protected fetching, free-only discovery, report-only
  writes, current-run retrieval/write receipts and structural report validation.
- **Source Evidence**: Bounded in-memory excerpts with explicit coverage and
  truncation flags for advisory review; receipts are not factual proof.

Research tool profiles omit shell execution, generic editing and delegation.
Public searches transmit queries to discovery services even when inference stays
local. See [research tools](../../docs/repo-assistant/research.md) and
[privacy boundaries](../../docs/repo-assistant/permissions.md).
