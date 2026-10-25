"""Selection must preserve coverage, opt-ins, and the Council import boundary."""

import importlib.util
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run-tests.py"
SPEC = importlib.util.spec_from_file_location("run_test_suites", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
suites = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suites)


class TestSuiteSelection:
    def test_child_environment_drops_repository_overrides_without_mutating_parent(
        self, monkeypatch
    ):
        overrides = {
            "GIT_DIR": "sender/.git",
            "GIT_WORK_TREE": "sender",
            "GIT_INDEX_FILE": "sender/.git/index",
            "GIT_COMMON_DIR": "sender/.git",
            "GIT_CONFIG_PARAMETERS": "'core.bare'='true'",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.bare",
            "GIT_CONFIG_VALUE_0": "true",
        }
        for name, value in overrides.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
        environment = suites.test_environment()
        assert not overrides.keys() & environment.keys()
        assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
        assert environment["GIT_TERMINAL_PROMPT"] == "0"
        assert all(os.environ[name] == value for name, value in overrides.items())

    def test_push_hook_keeps_fixture_git_operations_out_of_sender(self, tmp_path):
        """Exercise the real hook environment without touching an external remote."""
        sender = tmp_path / "sender"
        receiver = tmp_path / "receiver.git"
        fixture = tmp_path / "fixture"
        child_bare = tmp_path / "child.git"
        environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"}

        def git(*arguments, cwd=tmp_path):
            result = subprocess.run(
                ["git", *arguments],
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            assert result.returncode == 0, result.stderr[-5000:]
            return result.stdout.strip()

        git("init", "--quiet", str(sender))
        git("init", "--quiet", "--bare", str(receiver))
        (sender / "source.txt").write_text("sender must stay unchanged\n")
        git("add", "source.txt", cwd=sender)
        git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "sender",
            cwd=sender,
        )
        head = git("rev-parse", "HEAD", cwd=sender)
        index = (sender / ".git/index").read_bytes()
        config = (sender / ".git/config").read_bytes()
        child_code = (
            "import os, pathlib, subprocess, sys\n"
            "assert not any(k in os.environ for k in "
            "('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_CONFIG_PARAMETERS'))\n"
            "assert os.environ['GIT_TERMINAL_PROMPT'] == '0'\n"
            "assert os.environ['GIT_CONFIG_NOSYSTEM'] == '1'\n"
            "fixture, bare = map(pathlib.Path, sys.argv[1:])\n"
            "def git(*args): subprocess.run(['git', *args], check=True, timeout=10)\n"
            "git('init', '--quiet', str(fixture))\n"
            "(fixture/'source.txt').write_text('independent fixture\\n')\n"
            "git('-C', str(fixture), 'add', 'source.txt')\n"
            "git('-C', str(fixture), '-c', 'user.name=Fixture', '-c', "
            "'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', "
            "'commit', '--quiet', '-m', 'fixture')\n"
            "git('init', '--quiet', '--bare', str(bare))\n"
        )
        worker = tmp_path / "hook_worker.py"
        worker.write_text(
            "import importlib.util,sys\n"
            f"spec=importlib.util.spec_from_file_location('runner',{str(SCRIPT)!r})\n"
            "runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)\n"
            f"runner.test_commands=lambda *args: [[sys.executable,'-c',{child_code!r},"
            f"{str(fixture)!r},{str(child_bare)!r}]]\n"
            "raise SystemExit(runner.main(['cli']))\n",
            encoding="utf-8",
        )
        hooks = sender / ".git/hooks"
        hook = hooks / "pre-push"
        hook.write_text(
            "#!/bin/sh\nexec "
            + shlex.quote(Path(sys.executable).as_posix())
            + " "
            + shlex.quote(worker.as_posix())
            + "\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        git(
            "-c",
            f"core.hooksPath={hooks.as_posix()}",
            "push",
            "--quiet",
            str(receiver),
            "HEAD:refs/heads/checked",
            cwd=sender,
        )
        assert git("rev-parse", "HEAD", cwd=sender) == head
        assert (sender / ".git/index").read_bytes() == index
        assert (sender / ".git/config").read_bytes() == config
        assert git("rev-parse", "refs/heads/checked", cwd=receiver) == head
        assert git("rev-parse", "HEAD", cwd=fixture) != head
        assert git("rev-parse", "--is-bare-repository", cwd=child_bare) == "true"

    @pytest.mark.parametrize("option", ["--junitxml=report.xml", "--junit-xml=report.xml"])
    def test_full_preserves_both_junit_reports(self, option):
        commands = suites.test_commands(["full"], [option])
        assert commands[0][-1].endswith("report-workspace.xml")
        assert commands[1][-1].endswith("report-council.xml")
        assert commands[2][-1].endswith("report-job-search.xml")

    def test_full_excludes_live_and_runs_council_separately(self):
        commands = suites.test_commands(["full"], ["-q"])
        assert len(commands) == 3
        assert "tests/test_ide_bridge.py" in commands[0]
        assert all("tests/integration/" not in path for command in commands for path in command)
        assert all("apps/ai_council/" not in path for path in commands[0])
        assert "apps/ai_council/tests/test_council.py" in commands[1]
        assert "apps/job_search/job-email/test_job_search.py" in commands[2]
        assert all(command[-1] == "-q" for command in commands)

    @pytest.mark.parametrize("directory", ["tests", "apps/new_app", "packages/new_package"])
    def test_new_unassigned_test_fails_selection(self, tmp_path, directory):
        # Copy filenames only; the selector must never import or execute test files.
        for patterns in suites.GROUPS.values():
            for pattern in patterns:
                target = tmp_path / pattern.replace("*", "fixture")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
        target = tmp_path / directory / "test_unassigned.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        with pytest.raises(ValueError, match="test_unassigned.py"):
            suites.suite_files(tmp_path)

    def test_combining_groups_deduplicates_modules(self):
        (command,) = suites.test_commands(["agent", "agent"], [])
        assert command.count("tests/test_ide_bridge.py") == 1

    def test_failure_status_survives_later_success(self, monkeypatch):
        from types import SimpleNamespace

        statuses = iter((1, 0, 0))
        monkeypatch.setattr(
            suites.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=next(statuses))
        )
        assert suites.main(["full", "--", "-q"]) == 1
