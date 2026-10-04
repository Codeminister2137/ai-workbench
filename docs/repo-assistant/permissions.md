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
