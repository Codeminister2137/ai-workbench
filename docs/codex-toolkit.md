# Codex Toolkit Notes

This file records reusable Codex/PyCharm setup that may later be transferred to
other projects. It is operational tooling context, not an architecture decision.

## PyCharm Codex Approval Watcher

Purpose: keep JetBrains PyCharm's integrated Codex agent on workspace-write
execution without repeated file-edit approval prompts.

Observed issue:

- PyCharm 2025.3 can rewrite
  `C:\Users\Jakub\AppData\Local\JetBrains\PyCharm2025.3\aia\codex\config.toml`
  back to `approval_policy = "on-request"` during Codex startup.
- Setting the file to read-only prevents PyCharm from initializing the ACP
  process, so read-only config is not viable.
- The desired behavior is:

```toml
approval_policy = "never"
sandbox_mode = "workspace-write"
```

Current workaround:

- A user-startup watcher rewrites `config.toml` back to `approval_policy =
  "never"` if PyCharm changes it.
- SQLite triggers in Codex's `state_5.sqlite` force AI-projects thread rows to
  `approval_mode = "never"`.
- This does not replace product/architecture/security decision approvals in
  `AGENTS.md`; it only removes repeated runtime file-permission prompts.

Installed paths:

```text
C:\Users\Jakub\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\CodexApprovalNeverWatcher.cmd
C:\Users\Jakub\AppData\Local\JetBrains\PyCharm2025.3\aia\codex\approval-workaround-backups\codex_approval_never_watcher.ps1
C:\Users\Jakub\AppData\Local\JetBrains\PyCharm2025.3\aia\codex\approval-workaround-backups\revert_ai_projects_approval_workaround.ps1
```

Verification:

```powershell
Get-Content "$env:LOCALAPPDATA\JetBrains\PyCharm2025.3\aia\codex\config.toml" -Raw
& "$env:LOCALAPPDATA\JetBrains\PyCharm2025.3\aia\codex\bin\codex-x86_64-pc-windows-msvc.exe" doctor
```

Expected `doctor` output includes:

```text
approval policy Never
filesystem sandbox restricted
network sandbox restricted
```

Revert:

```powershell
python "$env:LOCALAPPDATA\JetBrains\PyCharm2025.3\aia\codex\approval-workaround-backups\revert_ai_projects_approval_workaround.py"
```

If the PowerShell revert script exists and is newer, prefer:

```powershell
& "$env:LOCALAPPDATA\JetBrains\PyCharm2025.3\aia\codex\approval-workaround-backups\revert_ai_projects_approval_workaround.ps1"
```

Transfer note:

- Treat this as a local JetBrains/Codex integration workaround.
- Re-check the target IDE version and Codex paths before transferring.
- Prefer an official PyCharm/Codex setting if JetBrains later exposes a
  workspace-write/no-approval mode.
