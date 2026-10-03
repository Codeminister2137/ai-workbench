"""Real local process boundary tests, without network or inference."""

import json
import math
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path

import pytest
from ai_provider.orchestrated_runs import OrchestratedStagePlanItem, SQLiteOrchestratedRunStore
from ai_provider.research_runner import main, supervise_research


@pytest.fixture
def unfinished_run(tmp_path):
    store = SQLiteOrchestratedRunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        repo_root=tmp_path,
        mode="implement",
        prompt="research",
        budget_seconds=5,
        approval_policy="trusted_local",
        primary_route_id=None,
        primary_provider="ollama",
        primary_model="test",
        status="running",
        execution_status="running",
    )
    store.replace_stage_plan(
        run.run_id,
        [
            OrchestratedStagePlanItem(name, "local", "test")
            for name in ("implementation", "validation", "scrutiny", "final_handoff")
        ],
    )
    store.start_stage(
        run.run_id,
        "implementation",
        details={
            "fetch_receipts": [{"final_url": "https://example.com"}],
            "report_receipts": [{"sha256": "saved-report"}],
        },
    )
    (tmp_path / "report.md").write_text("saved partial report", encoding="utf-8")
    return store, run.run_id


@pytest.mark.parametrize("exit_code", [0, 3])
def test_unfinished_worker_exit_records_failure_and_preserves_saved_work(
    tmp_path, unfinished_run, exit_code
):
    store, run_id = unfinished_run
    output = []
    log = tmp_path / "research.log"
    code = supervise_research(
        [
            sys.executable,
            "-u",
            "-c",
            f"print('away_run_id: {run_id}', flush=True); raise SystemExit({exit_code})",
        ],
        root=tmp_path,
        database=store.path,
        budget_seconds=5,
        output=output.append,
        log_path=log,
    )
    assert code == (exit_code or 1)
    run = store.get_run(run_id)
    assert run is not None and run.status == "failed" and run.execution_status == "failed"
    stages = {stage.name: stage for stage in store.list_stages(run_id)}
    assert stages["implementation"].status == "failed"
    assert stages["implementation"].details["fetch_receipts"]
    assert stages["implementation"].details["report_receipts"]
    assert stages["validation"].status == stages["scrutiny"].status == "skipped"
    assert stages["final_handoff"].status == "completed"
    assert stages["final_handoff"].details["execution_status"] == "failed"
    assert stages["final_handoff"].details["validation_status"] == "planned"
    assert "before durable finalization" in log.read_text(encoding="utf-8")
    assert (tmp_path / "report.md").read_text() == "saved partial report"


@pytest.mark.parametrize("exit_code", [0, 3])
def test_worker_exit_preserves_existing_terminal_handoff(tmp_path, unfinished_run, exit_code):
    store, run_id = unfinished_run
    store.complete_stage(run_id, "implementation")
    store.complete_stage(run_id, "validation", details={"validation_status": "passed"})
    store.complete_stage(run_id, "scrutiny", details={"verdict": "pass"})
    store.complete_stage(run_id, "final_handoff", details={"owner_review": "preserve"})
    store.update_run_status(run_id, status="completed", execution_status="completed")
    before = store.list_stages(run_id)
    assert (
        supervise_research(
            [
                sys.executable,
                "-u",
                "-c",
                f"print('away_run_id: {run_id}', flush=True); raise SystemExit({exit_code})",
            ],
            root=tmp_path,
            database=store.path,
            budget_seconds=5,
            output=lambda line: None,
        )
        == exit_code
    )
    assert store.list_stages(run_id) == before
    assert store.get_run(run_id).execution_status == "completed"


def test_interruption_records_failure_after_draining_worker_output(tmp_path, unfinished_run):
    store, run_id = unfinished_run
    log = tmp_path / "research.log"
    output = []

    def interrupt(line):
        output.append(line)
        if line.startswith("away_run_id:"):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        supervise_research(
            [
                sys.executable,
                "-u",
                "-c",
                f"import time; print('away_run_id: {run_id}', flush=True); time.sleep(60)",
            ],
            root=tmp_path,
            database=store.path,
            budget_seconds=5,
            output=interrupt,
            log_path=log,
        )
    assert store.get_run(run_id).execution_status == "failed"
    handoff = next(stage for stage in store.list_stages(run_id) if stage.name == "final_handoff")
    assert handoff.details["execution_status"] == "failed"
    assert "supervisor interrupted" in log.read_text(encoding="utf-8")


def test_broken_output_during_cleanup_still_records_run_handoff(tmp_path, unfinished_run):
    store, run_id = unfinished_run
    log = tmp_path / "research.log"
    errors = []

    def broken_output(line):
        error = BrokenPipeError(f"Closed output: {line}")
        errors.append(error)
        raise error

    with pytest.raises(BrokenPipeError) as raised:
        supervise_research(
            [
                sys.executable,
                "-u",
                "-c",
                f"print('away_run_id: {run_id}'); "
                "print('queued progress'); print('final progress')",
            ],
            root=tmp_path,
            database=store.path,
            budget_seconds=5,
            output=broken_output,
            log_path=log,
        )
    assert raised.value is errors[0]
    assert store.get_run(run_id).execution_status == "failed"
    handoff = next(stage for stage in store.list_stages(run_id) if stage.name == "final_handoff")
    assert handoff.details["execution_status"] == "failed"
    assert "supervisor interrupted" in log.read_text(encoding="utf-8")


def test_worker_exit_does_not_create_missing_run_database(tmp_path):
    database = tmp_path / "missing.sqlite3"
    assert (
        supervise_research(
            [sys.executable, "-u", "-c", "raise SystemExit(3)"],
            root=tmp_path,
            database=database,
            budget_seconds=5,
            output=lambda line: None,
        )
        == 3
    )
    assert not database.exists()


def test_worker_without_run_id_does_not_modify_another_run(tmp_path, unfinished_run):
    store, run_id = unfinished_run
    before = store.get_run(run_id), store.list_stages(run_id)
    assert (
        supervise_research(
            [sys.executable, "-u", "-c", "raise SystemExit(3)"],
            root=tmp_path,
            database=store.path,
            budget_seconds=5,
            output=lambda line: None,
        )
        == 3
    )
    assert (store.get_run(run_id), store.list_stages(run_id)) == before


def test_terminal_unicode_failure_does_not_abort_worker_progress(monkeypatch):
    from ai_provider.research_runner import print_progress

    class Terminal(StringIO):
        encoding = "ascii"

        def write(self, value):
            value.encode("ascii")
            return super().write(value)

    terminal = Terminal()
    monkeypatch.setattr(sys, "stdout", terminal)
    print_progress("Research source\u2011grounded 日本語")
    assert "Research source?grounded ???" in terminal.getvalue()


def test_supervisor_preserves_arguments_unicode_and_worker_exit_code(tmp_path):
    output = []
    value = 'Research "quoted words" and 日本語'
    code = supervise_research(
        [sys.executable, "-u", "-c", "import sys; print(sys.argv[1]); sys.exit(3)", value],
        root=tmp_path,
        database=tmp_path / "runs.sqlite3",
        budget_seconds=5,
        output=output.append,
    )
    assert code == 3
    assert value in output
    assert output[-1] == "research_supervisor_status: failed"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell native argument boundary")
def test_research_launcher_preserves_legacy_native_quotes_and_backslashes(tmp_path):
    values = [
        'Research "quoted words" and 日本語',
        'Read \\"literal escaped quotes\\"',
        "C:\\folder with spaces\\",
        '"quoted"',
        'two lines\nwith quotes: "value"',
    ]
    arguments = tmp_path / "arguments.json"
    arguments.write_text(json.dumps(values), encoding="utf-8")
    echo = tmp_path / "echo.py"
    echo.write_text("import json, sys; print(json.dumps(sys.argv[1:]))", encoding="utf-8")
    probe = tmp_path / "probe.ps1"
    probe.write_text(
        """param($Wrapper, $Python, $Echo, $Arguments)
$tokens = $null; $issues = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile(
    $Wrapper, [ref]$tokens, [ref]$issues)
$definition = $tree.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'ConvertTo-LegacyNativeArgument'
}, $true)
Invoke-Expression $definition.Extent.Text
$values = Get-Content -LiteralPath $Arguments -Raw -Encoding UTF8 | ConvertFrom-Json
$escaped = @($values | ForEach-Object { ConvertTo-LegacyNativeArgument $_ })
& $Python $Echo @escaped
exit $LASTEXITCODE
""",
        encoding="utf-8",
    )
    wrapper = Path(__file__).resolve().parents[1] / "scripts/repo-assistant-research.ps1"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(probe),
            str(wrapper),
            sys.executable,
            str(echo),
            str(arguments),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    assert json.loads(result.stdout) == values


def test_supervisor_deadline_is_not_extended_by_progress(tmp_path):
    output = []
    started = time.monotonic()
    code = supervise_research(
        [
            sys.executable,
            "-u",
            "-c",
            "import time\nwhile True:\n print('still working', flush=True)\n time.sleep(.05)",
        ],
        root=tmp_path,
        database=tmp_path / "runs.sqlite3",
        budget_seconds=0.4,
        output=output.append,
    )
    assert code == 124
    assert time.monotonic() - started < 7
    assert "still working" in output


def test_supervisor_persists_timeout_marker_even_before_worker_creates_log(tmp_path):
    log_path = tmp_path / "logs" / "research.log"
    assert (
        supervise_research(
            [sys.executable, "-u", "-c", "import time; time.sleep(60)"],
            root=tmp_path,
            database=tmp_path / "runs.sqlite3",
            budget_seconds=0.3,
            output=lambda line: None,
            log_path=log_path,
        )
        == 124
    )
    assert "research_supervisor_status: timeout" in log_path.read_text(encoding="utf-8")


def test_timeout_records_handoff_and_preserves_receipts_and_partial_report(tmp_path):
    worker = """import time
from pathlib import Path
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore, OrchestratedStagePlanItem
store = SQLiteOrchestratedRunStore(Path('runs.sqlite3'))
run = store.create_run(repo_root=Path.cwd(), mode='implement', prompt='test', budget_seconds=1,
    approval_policy='trusted_local', primary_route_id=None,
    primary_provider='ollama', primary_model='test')
store.replace_stage_plan(run.run_id, [OrchestratedStagePlanItem(name, 'local', 'test')
    for name in ('implementation', 'validation', 'final_handoff')])
store.start_stage(run.run_id, 'implementation', details={'fetch_receipts': [{'final_url': 'https://example.com'}]})
Path('report.md').write_text('partial report')
print('away_run_id: ' + run.run_id, flush=True)
time.sleep(60)
"""
    output = []
    database = tmp_path / "runs.sqlite3"
    assert (
        supervise_research(
            [sys.executable, "-u", "-c", worker],
            root=tmp_path,
            database=database,
            budget_seconds=1.5,
            output=output.append,
        )
        == 124
    )
    run_id = next(
        line.removeprefix("away_run_id: ") for line in output if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(database)
    run = store.get_run(run_id)
    assert run is not None and run.status == "timeout" and run.execution_status == "timeout"
    stages = {stage.name: stage for stage in store.list_stages(run_id)}
    assert stages["implementation"].status == "timeout"
    details = stages["implementation"].details
    assert details is not None
    assert details["fetch_receipts"] == [{"final_url": "https://example.com"}]
    assert stages["final_handoff"].status == "completed"
    assert (tmp_path / "report.md").read_text() == "partial report"


def test_supervisor_stops_owned_descendants(tmp_path):
    marker = tmp_path / "late.txt"
    child = (
        "import time; from pathlib import Path; time.sleep(2); "
        "Path('late.txt').write_text('escaped')"
    )
    worker = (
        f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "time.sleep(60)"
    )
    assert (
        supervise_research(
            [sys.executable, "-u", "-c", worker],
            root=tmp_path,
            database=tmp_path / "runs.sqlite3",
            budget_seconds=0.5,
            output=lambda line: None,
        )
        == 124
    )
    time.sleep(2)
    assert not marker.exists()


@pytest.mark.parametrize("budget", [0, -1, math.inf, math.nan])
def test_supervisor_rejects_invalid_budget_before_spawning(tmp_path, budget):
    with pytest.raises(ValueError):
        supervise_research(
            [], root=tmp_path, database=tmp_path / "runs.sqlite3", budget_seconds=budget
        )


def test_unattended_runner_rejects_interactive_approvals():
    with pytest.raises(SystemExit):
        main(
            [
                "research",
                "--away-minutes",
                "1",
                "--tool-profile",
                "research",
                "--approval-policy",
                "interactive",
            ]
        )
