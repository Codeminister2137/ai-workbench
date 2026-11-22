"""Fresh continuation; prior interrupted trial remains unscored."""

import ast
import hashlib
import runpy
import sys

ns = runpy.run_path("docs/repo-assistant/health-deep-48679817.py")
ROOT = ns["ROOT"]
load = ns["load"]
write = ns["write"]
run = ns["run"]
tests = ns["tests"]
OUT = ROOT / ".tmp/health-48679817-reserve"
OUT.mkdir(exist_ok=False)
# Imported helpers retain their defining global namespace.
ns["write"].__globals__["OUT"] = OUT
suites = load("health_suites", "scripts/run-tests.py")
ns["run"].__globals__["suites"] = suites
selector = load("health_selector", "scripts/affected-tests-prototype.py")
groups = suites.suite_files()
trials = [
    (
        "cross-component",
        "packages/ai_orchestrator/src/ai_orchestrator/repair.py",
        "budget_seconds * 0.1",
        "budget_seconds * 0.2",
    )
]
write(
    "bounds.json",
    {
        "outer_seconds": 900,
        "max_test_processes": 9,
        "per_process_timeout_seconds": 300,
        "retries": 0,
        "scope": "focused repair baseline after preserved full baseline socket failure; one cross-component comparison, coverage, deletion; full tests unchanged; any unrelated failure reported separately",
        "prior_interruption": "original interrupted trial and subsequent 300s liveness mutation preserved, not replayed or scored; different mutation now tested",
        "stop": "baseline or infrastructure failure stops admission; source restored in finally",
    },
)
baseline = {
    "commands": [
        run(
            "focused-baseline",
            [sys.executable, "-m", "pytest", "tests/test_repair_progress.py", "-q", "-n", "0"],
            120,
        )
    ],
    "failures": [],
}
if baseline["failures"] or any(r["exit"] for r in baseline["commands"]):
    raise SystemExit("Baseline failed; stop")
if True:
    for label, relative, old, new in trials:
        path = ROOT / relative
        original = path.read_bytes()
        text = original.decode("utf-8")
        assert text.count(old) == 1
        selection = selector.select_groups([relative], groups)
        write(f"{label}-selection.json", selection)
        try:
            path.write_bytes(text.replace(old, new).encode("utf-8"))
            selected = tests(f"{label}-selected", selection["groups"])
            full = tests(f"{label}-full", ["full"])
            write(
                f"{label}-comparison.json",
                {
                    "full_failures": full["failures"],
                    "selected_failures": selected["failures"],
                    "missed": sorted(set(full["failures"]) - set(selected["failures"])),
                    "selected_cases": len(selected["cases"]),
                    "full_cases": len(full["cases"]),
                    "selected_seconds": selected["seconds"],
                    "full_seconds": full["seconds"],
                    "hash_before": hashlib.sha256(original).hexdigest(),
                    "hash_mutated": hashlib.sha256(path.read_bytes()).hexdigest(),
                },
            )
        finally:
            path.write_bytes(original)
            write(
                f"{label}-restored.json",
                {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "matches_original": path.read_bytes() == original,
                },
            )
    target = "packages/ai_provider/src/ai_provider/aider_polyglot_scores.py"
    coverage = run(
        "coverage",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_aider_polyglot_scores.py",
            "-q",
            "-n",
            "0",
            "--cov=ai_provider.aider_polyglot_scores",
            "--cov-branch",
            f"--cov-report=json:{OUT / 'coverage-data.json'}",
        ],
        120,
    )
    if coverage["exit"]:
        raise SystemExit("Coverage baseline failed")
    path = ROOT / target
    original = path.read_bytes()
    tree = ast.parse(original)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_PolyglotParser")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "handle_data")
    try:
        lines = original.decode("utf-8").splitlines(keepends=True)
        del lines[method.lineno - 1 : method.end_lineno]
        path.write_bytes("".join(lines).encode("utf-8"))
        run(
            "deletion",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_aider_polyglot_scores.py",
                "-q",
                "-n",
                "0",
            ],
            120,
        )
    finally:
        path.write_bytes(original)
        write(
            "deletion-restored.json",
            {
                "matches_original": path.read_bytes() == original,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        )
    write("finished.json", {"status": "experiments_finished", "not_gate_adoption": True})
