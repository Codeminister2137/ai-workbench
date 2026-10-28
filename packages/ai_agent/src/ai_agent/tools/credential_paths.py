"""Credential-file refusal for project-owned tools, not an OS sandbox."""

from pathlib import Path


def is_credential_path(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    if not parts:
        return False
    name = parts[-1]
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    if name in {".modal.toml", ".git-credentials", ".netrc", ".pypirc", ".npmrc"}:
        return True
    if len(parts) >= 2:
        parent = parts[-2]
        if (
            (parent in {".codex", "opencode"} and name == "auth.json")
            or (parent == ".aws" and name == "credentials")
            or (parent == ".docker" and name == "config.json")
        ):
            return True
        if parent == ".ssh" and name.startswith("id_") and not name.endswith(".pub"):
            return True
    return False
