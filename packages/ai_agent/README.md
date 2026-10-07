# ai-agent

Agentic tool execution loop, tool registry, permission policies, and
multi-turn coding session management built on top of `ai_orchestrator` and
`ai_provider`.

## Features

- **Provider-Neutral Tool Registry**: Define tools with strict JSON schemas
  and run them across local and hosted models.
- **Built-in Coding Tools**: Safe file reading, slice editing, creation,
  directory listing, regex/grep search, bounded local Git status/diff, and
  shell execution.
- **Permission and Safety Control**: Configurable approval policies for read
  vs. write vs. command execution, with workspace boundary enforcement.
- **Authorization Boundary**: Secret-free contracts for external service
  authorization state, read/write grants, credential locations, and reusable
  diagnostics.
- **Agent Loop**: Provider-neutral multi-turn tool-calling cycle with
  permission enforcement, tool-result messages, and iteration limits.
- **Public Research Tools**: Protected fetching, free-only discovery,
  report-only writes, current-run retrieval/write receipts, and structural
  report validation.
- **Source Evidence**: Bounded in-memory excerpts with explicit coverage and
  truncation flags for advisory review; receipts are not factual proof.
- **Python Runtime Diagnostics**: Read-only inspector that reports the active
  interpreter, workspace environment hints, and `uv.lock` presence without
  executing code.
- **Semantic Rename (optional)**: Preview-first Python symbol rename using the
  optional Jedi dependency. Produces a reviewable diff before any file
  changes and enforces human approval for the write step.

Research tool profiles omit shell execution, generic editing, and delegation.
Public searches transmit queries to discovery services even when inference
stays local. See [research tools](../../docs/repo-assistant/research.md) and
[privacy boundaries](../../docs/repo-assistant/permissions.md).

## Structure

```text
src/ai_agent/
  __init__.py          # top-level public API
  contracts.py         # ToolDefinition, ToolCall, ToolResult, ToolCategory
  loop.py              # AgentLoop, AgentResult
  permissions.py       # PermissionManager, ApprovalPolicyPreset
  authorization.py     # secret-free external-service authorization contracts
  codex_authorization.py
  tool_profiles.py     # profile builders for coding, research, shared routes
  skills.py            # skill registration and prerequisite checks
  shared_approvals.py  # MCP shared-tool approval contracts
  http_host.py         # per-invocation foreground MCP HTTP host
  ide_bridge.py        # read-only PyCharm/IDE wrappers (optional SDK)
  tools/
    __init__.py        # default_coding_tools(), exports all tool classes
    base.py            # BaseTool, ToolContext, ToolRegistry
    filesystem.py      # ReadFileTool, EditFileTool, CreateFileTool, ListDirTool
    search.py          # GrepSearchTool, FindFilesTool
    git.py             # GitStatusTool, GitDiffTool
    shell.py           # RunCommandTool
    delegation.py      # DelegateTaskTool, coding_tools_with_delegation()
    python_runtime.py  # PythonRuntimeTool
    refactor.py        # PythonNavigateTool, RenamePreviewTool, RenameApplyTool
```

## Tools reference

| Tool | Category | Description |
| --- | --- | --- |
| `ReadFileTool` | READ | Read file lines with optional offset/limit |
| `EditFileTool` | WRITE | Replace exact line ranges in an existing file |
| `CreateFileTool` | WRITE | Create or overwrite a file |
| `ListDirTool` | READ | List directory contents within the workspace |
| `GrepSearchTool` | READ | Regex search across workspace files |
| `FindFilesTool` | READ | Find files matching a glob pattern |
| `GitStatusTool` | READ | Bounded `git status` output |
| `GitDiffTool` | READ | Bounded `git diff` output |
| `RunCommandTool` | SHELL | Run a shell command with workspace containment |
| `DelegateTaskTool` | DELEGATE | Delegate a subtask to a separate agent invocation |
| `PythonRuntimeTool` | READ | Report the active Python interpreter and workspace hints |
| `PythonNavigateTool` | READ | Find Python symbol definitions and references (requires optional Jedi) |
| `RenamePreviewTool` | READ | Preview a Python symbol rename as a reviewable diff (requires optional Jedi) |
| `RenameApplyTool` | WRITE | Apply a reviewed rename plan atomically (requires optional Jedi) |

## Minimal usage

```python
from pathlib import Path
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.factory import create_chat_client
from ai_agent import AgentLoop, ApprovalPolicyPreset, PermissionManager
from ai_agent.tools import default_coding_tools

client = create_chat_client(
    BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2")
)

permissions = PermissionManager(
    preset=ApprovalPolicyPreset.READ_ONLY,
    workspace_root=Path("."),
)

tools = default_coding_tools()
loop = AgentLoop(client, tools, permissions, workspace_root=Path("."))
result = loop.run("List the top-level Python files in this workspace.")
print(result.final_response)
```

## Approval policies

| Preset | Allowed operations |
| --- | --- |
| `READ_ONLY` | Read, search, Git status/diff, Python runtime/navigation |
| `WORKSPACE_WRITE` | Above + file create/edit; shell requires interactive approval |
| `INTERACTIVE` | Above + interactive human approval for shell and destructive writes |
| `TRUSTED_LOCAL` | All tools without interactive prompts |

## Optional dependencies

Semantic rename and Python navigation require the optional `rename-preview`
extra:

```powershell
python -m uv sync --extra rename-preview
```

The IDE bridge requires the optional `ide` extra (official MCP SDK):

```powershell
python -m uv sync --extra ide
```

## Tests

```powershell
python -m uv run pytest tests/test_ai_agent_tools.py tests/test_ai_agent_permissions.py
python -m uv run pytest tests/test_python_runtime_tool.py tests/test_semantic_refactor.py
```
