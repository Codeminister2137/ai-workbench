# Permissions, logging and privacy

[CLI guide](../repo-coding-assistant.md) Â· [Privacy and permissions](permissions.md)

## Permission Boundary

Default behavior:

- selected files inside the repo are read automatically;
- selected files outside the repo ask first;
- assistant action paths or command working directories outside the repo ask
  first;
- provider calls happen only with `--execute`;
- executed provider `implement` routes use native tools by default; the selected
  `--approval-policy` controls them (`interactive` asks before writes and shell);
- `--apply-actions` enables the legacy fenced-JSON action path; use
  `--no-native-tools` when intentionally selecting that path.

Native file tools reject outside-workspace paths. The shell tool checks its
working directory but does not sandbox the command's effects; a shell grant is
broader than a workspace-file grant. External clients have their own restrictions
and only supported policy mappings are accepted. Read-only Git status/diff tools
use fixed commands under READ permissions; they do not grant general shell access.
These calls disable configured clean/process content filters as well as external
diff and text-conversion helpers. Filtered repositories receive a visible notice:
the comparison uses raw worktree content and can differ from ordinary Git output.
Unsafe filter override names are refused; repository configuration is unchanged.
Submodule content is not traversed; Git pointer changes remain visible. Inspect a
submodule's content by selecting its own workspace explicitly.

The opt-in [shared coding profile](common-inspection.md#shared-coding-and-terminal-approvals)
enforces these presets in the project MCP server. Interactive requests use the
controlling terminal, require approval for each exact operation and refuse when
no human terminal is available. Task/run/workspace scope and foreground process
identity prevent inherited grants after owner exit. Shared inspection remains
read-only. Existing coding sessions persist scoped digest receipts without raw
tool arguments or outputs. Bounded `workspace_write` continuation through real
Copilot and Kiro passed. On 2026-10-06, an owner-approved exact file creation
passed through the live foreground MCP host and controlling-terminal approval
handler; the confirmation was supplied in chat and relayed to the waiting local
terminal. This verifies one approved write, not a human typing into the terminal,
shell approval, or general client parity.

For an assistant-initiated live acceptance that can block on terminal approval,
the assistant must first tell the owner the exact command, working directory,
expected effects and approval prompt, then wait for explicit confirmation that
the owner is present and ready before launching it. Prior approval of the
acceptance plan does not establish availability for a later prompt. If the
owner is not ready, defer the command; do not start it in the background or
relay a chat response as if it were physical terminal input.

Python semantic rename is separate from the read-only IDE bridge. The coding
profile's `rename_preview` does not modify files; `rename_apply` is WRITE and
approval displays the full immutable diff and digest. The optional Jedi extra,
expiry, workspace/digest checks and partial-effect semantics are documented in
[the semantic rename contract](semantic-refactoring-proposal.md).

Avoid `--allow-outside-files` unless you deliberately want to allow outside-repo
paths without a prompt.

## Important Precautions

- Review `git diff` after any run that could write files.
- Start with local Ollama for private or sensitive code.
- Use hosted providers only when you are comfortable sending the selected
  context to that external provider.
- Keep API keys in the process environment or an ignored local `.env`, never
  in committed files.
- Do not pass broad directories or secrets as context.
- The action loop can write files and run commands inside the repo. Treat it as
  a coding assistant, not as a fully trusted autonomous agent.

Useful checks after a run:

```powershell
git diff
git status --short
python -m uv run pytest tests\repo_assistant
```
