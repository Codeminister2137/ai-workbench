"""Acceptance contracts for early request dispatch and admission ordering."""

import pytest
from ai_agent import repo_coding_assistant as cli


@pytest.mark.parametrize(
    "flags,handler",
    [
        (["--list-skills"], "_print_skill_discovery"),
        (["--fallback-readiness"], "_print_fallback_readiness"),
        (["--codex-login"], "_run_codex_login"),
        (["--codex-login-device"], "_run_codex_login"),
        (["--codex-plugin-install", "fixture"], "_run_codex_plugin_management"),
        (["--codex-plugin-remove", "fixture"], "_run_codex_plugin_management"),
    ],
)
@pytest.mark.parametrize("exit_status", [0, 1])
def test_setup_dispatch_returns_status_before_prompt_or_route_validation(
    tmp_path, monkeypatch, flags, handler, exit_status
):
    calls = []

    def handle(*args, **kwargs):
        calls.append((args, kwargs))
        return exit_status

    monkeypatch.setattr(cli, handler, handle)
    monkeypatch.setattr(
        cli, "prepare_execution", lambda *a, **kw: pytest.fail("setup must not select a route")
    )
    assert cli.main(["--repo-root", str(tmp_path), *flags]) == exit_status
    assert len(calls) == 1


def test_setup_dispatch_preserves_login_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_run_codex_login", lambda **kwargs: 0)
    monkeypatch.setattr(
        cli, "_run_codex_plugin_management", lambda **kwargs: pytest.fail("login takes precedence")
    )
    assert (
        cli.main(
            ["--repo-root", str(tmp_path), "--codex-login", "--codex-plugin-install", "fixture"]
        )
        == 0
    )


def test_invalid_chat_arguments_fail_before_deadline_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli,
        "_configure_execution_deadline",
        lambda args: pytest.fail("invalid chat request admitted"),
    )
    with pytest.raises(SystemExit) as failure:
        cli.main(["prompt", "--repo-root", str(tmp_path), "--chat-list-limit", "0"])
    assert failure.value.code == 2
