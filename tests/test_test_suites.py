"""Selection must preserve coverage, opt-ins, and the Council import boundary."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run-tests.py"
SPEC = importlib.util.spec_from_file_location("run_test_suites", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
suites = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suites)


class TestSuiteSelection:
    @pytest.mark.parametrize("option", ["--junitxml=report.xml", "--junit-xml=report.xml"])
    def test_full_preserves_both_junit_reports(self, option):
        commands = suites.test_commands(["full"], [option])
        assert commands[0][-1].endswith("report-workspace.xml")
        assert commands[1][-1].endswith("report-council.xml")

    def test_full_excludes_live_and_runs_council_separately(self):
        commands = suites.test_commands(["full"], ["-q"])
        assert len(commands) == 2
        assert "tests/test_ide_bridge.py" in commands[0]
        assert all("tests/integration/" not in path for command in commands for path in command)
        assert all("apps/ai_council/" not in path for path in commands[0])
        assert "apps/ai_council/tests/test_council.py" in commands[1]
        assert all(command[-1] == "-q" for command in commands)

    def test_new_unassigned_test_fails_selection(self, tmp_path):
        # Copy filenames only; the selector must never import or execute test files.
        for patterns in suites.GROUPS.values():
            for pattern in patterns:
                target = tmp_path / pattern.replace("*", "fixture")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
        (tmp_path / "tests/test_unassigned.py").touch()
        with pytest.raises(ValueError, match="test_unassigned.py"):
            suites.suite_files(tmp_path)

    def test_combining_groups_deduplicates_modules(self):
        (command,) = suites.test_commands(["agent", "agent"], [])
        assert command.count("tests/test_ide_bridge.py") == 1

    def test_failure_status_survives_later_success(self, monkeypatch):
        from types import SimpleNamespace

        statuses = iter((1, 0))
        monkeypatch.setattr(
            suites.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=next(statuses))
        )
        assert suites.main(["full", "--", "-q"]) == 1
