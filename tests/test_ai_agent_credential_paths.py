"""Direct, filesystem-independent checks of the credential naming boundary."""

from pathlib import Path

import pytest
from ai_agent.tools.credential_paths import is_credential_path


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        ".env.production.local",
        ".env.example.backup",
        ".modal.toml",
        ".git-credentials",
        ".netrc",
        ".pypirc",
        ".npmrc",
        ".gitconfig",
        "secrets.yaml",
        "secrets.yml",
        "secrets.json",
        "service-account.json",
        "a.key",
        "long-service-private-key.pem",
        ".codex/auth.json",
        "opencode/auth.json",
        ".aws/credentials",
        ".docker/config.json",
        ".ssh/id_rsa",
        ".ssh/id_ed25519",
        ".ssh/id_future_algorithm",
        ".ssh/id_ed25519.pub.backup",
    ],
)
@pytest.mark.parametrize("prefix", ["", "workspace/nested/"])
@pytest.mark.parametrize("uppercase", [False, True])
def test_protected_names_fail_closed(name: str, prefix: str, uppercase: bool) -> None:
    candidate = prefix + name
    if uppercase:
        candidate = candidate.upper()
    assert is_credential_path(Path(candidate))


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        ".env.example",
        ".ENV.EXAMPLE",
        "env.local",
        ".environment",
        "archive.pem.txt",
        "monkey",
        "secrets.json.example",
        "service-account.json.template",
        "auth.json",
        "credentials",
        "config.json",
        "codex/auth.json",
        ".codex-backup/auth.json",
        ".aws-backup/credentials",
        ".docker-backup/config.json",
        ".ssh/id_ed25519.pub",
        ".SSH/ID_RSA.PUB",
        ".ssh/known_hosts",
        "ssh/id_rsa",
        "id_ed25519",
        ".env/readme.md",
        ".codex/nested/auth.json",
    ],
)
def test_safe_decoys_are_not_credentials(name: str) -> None:
    assert not is_credential_path(Path(name))
