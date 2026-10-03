# Permissions, logging and privacy

[CLI guide](../repo-coding-assistant.md) Â· [Privacy and permissions](permissions.md)

## Permission Boundary

Default behavior:

- selected files inside the repo are read automatically;
- assistant actions inside the repo are allowed automatically;
- selected files outside the repo ask first;
- assistant action paths or command working directories outside the repo ask
  first;
- provider calls happen only with `--execute`;
- local file/command actions happen only with `--apply-actions`.

Avoid `--allow-outside-files` unless you deliberately want to allow outside-repo
paths without a prompt.

## Important Precautions

- Review `git diff` after any run that used `--apply-actions`.
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
