"""Focused checks for E2E promotion checklists (ADR-087)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from e2e_promotion import (
    apply_ancestor_matching,
    area_for_path,
    build_report,
    change_summary,
    covers_range,
    find_ancestor_report,
    generate_checklist,
    is_ancestor,
    merge_diff_files,
    merges_between,
    promotion_verdict,
    uncovered_merges,
    verify_no_diff,
)


def test_area_mapping_covers_known_prefixes() -> None:
    area, _behavior, goal, _neighbors = area_for_path("apps/workbench_dashboard/x.py")
    assert area == "dashboard"
    assert goal == "docs/goals/dashboard.md"
    area, _behavior, _goal, _neighbors = area_for_path("packages/ai_provider/y.py")
    assert area == "provider"
    area, _behavior, _goal, _neighbors = area_for_path("docs/plan.md")
    assert area == "docs"


def test_area_mapping_falls_back_for_unknown_paths() -> None:
    area, _behavior, _goal, _neighbors = area_for_path("AGENTS.md")
    assert area == "docs"
    area, _behavior, _goal, _neighbors = area_for_path("unknown/blob.bin")
    assert area == "tooling"


def test_generate_groups_by_area_with_goals() -> None:
    checklist = generate_checklist(
        "abc123",
        ["apps/workbench_dashboard/a.py", "apps/workbench_dashboard/b.py"],
    )
    assert checklist["merge_commit"] == "abc123"
    kinds = {(item["kind"], item["area"]) for item in checklist["items"]}
    assert ("behavior", "dashboard") in kinds
    dashboard = next(i for i in checklist["items"] if i["area"] == "dashboard")
    assert dashboard["files"] == [
        "apps/workbench_dashboard/a.py",
        "apps/workbench_dashboard/b.py",
    ]
    assert dashboard["goals"] == ["docs/goals/dashboard.md"]
    assert dashboard["status"] == "pending"


def test_generate_adds_regression_neighbors() -> None:
    checklist = generate_checklist("abc123", ["packages/ai_provider/a.py"])
    kinds = {(item["kind"], item["area"]) for item in checklist["items"]}
    assert ("behavior", "provider") in kinds
    assert ("regression", "orchestrator") in kinds
    assert ("regression", "dashboard") in kinds


def test_generate_marks_docs_nonbehavioral() -> None:
    checklist = generate_checklist("abc123", ["docs/notes.md"])
    assert [(i["kind"], i["status"]) for i in checklist["items"]] == [("nonbehavioral", "pending")]


def test_generate_empty_diff_yields_no_items() -> None:
    assert generate_checklist("abc123", [])["items"] == []


def _report(commit: str, built: str, verdict: str = "pass") -> dict:
    return {
        "id": f"r-{commit}",
        "commit": commit,
        "overall": "pass",
        "built_utc": built,
        "items": [{"id": "behavior:dashboard", "verdict": verdict}],
    }


def test_find_ancestor_report_skips_non_ancestors() -> None:
    def runner(_root: str, *args: str) -> bytes:
        if args[:2] == ("merge-base", "--is-ancestor") and args[2] == "old":
            return b""
        raise RuntimeError("not ancestor")

    reports = [
        _report("old", "2026-01-01T00:00:00+00:00"),
        _report("new", "2026-02-01T00:00:00+00:00"),
    ]
    found = find_ancestor_report("behavior:dashboard", "tip", reports, ".", runner)
    assert found is not None and found["commit"] == "old"


def test_find_ancestor_report_requires_pass() -> None:
    def runner(_root: str, *args: str) -> bytes:
        return b""

    found = find_ancestor_report(
        "behavior:dashboard",
        "tip",
        [_report("old", "2026-01-01T00:00:00+00:00", "fail")],
        ".",
        runner,
    )
    assert found is None


def test_ancestor_matching_attaches_proof_and_warning() -> None:
    def runner(_root: str, *args: str) -> bytes:
        if args[0] == "merge-base":
            return b""
        return b""  # empty diff

    checklist = generate_checklist("tip", ["apps/workbench_dashboard/a.py"])
    out = apply_ancestor_matching(
        checklist, [_report("old", "2026-01-01T00:00:00+00:00")], ".", runner
    )
    dashboard = next(i for i in out["items"] if i["id"] == "behavior:dashboard")
    assert dashboard["status"] == "auto-pass"
    assert dashboard["verdict_by"] == "ancestor"
    assert dashboard["proof"]["diff_bytes"] == 0
    assert dashboard["proof"]["ancestor_commit"] == "old"
    assert "not re-tested" in dashboard["warning"]
    assert "old" in dashboard["warning"]


def test_ancestor_matching_refuses_changed_code() -> None:
    def runner(_root: str, *args: str) -> bytes:
        if args[0] == "merge-base":
            return b""
        return b"diff --git a/x b/x\n"  # nonempty diff

    checklist = generate_checklist("tip", ["apps/workbench_dashboard/a.py"])
    out = apply_ancestor_matching(
        checklist, [_report("old", "2026-01-01T00:00:00+00:00")], ".", runner
    )
    dashboard = next(i for i in out["items"] if i["id"] == "behavior:dashboard")
    assert dashboard["status"] == "pending"


def test_nonbehavioral_auto_pass_states_reason() -> None:
    checklist = generate_checklist("tip", ["docs/notes.md"])
    out = apply_ancestor_matching(checklist, [], ".")
    (item,) = out["items"]
    assert item["status"] == "auto-pass"
    assert item["verdict_by"] == "nonbehavioral"
    assert item["reason"]


def test_build_report_passes_only_when_all_pass() -> None:
    task = {
        "id": "t1",
        "merge_commit": "tip",
        "title": "t",
        "items": [
            {"id": "behavior:a", "kind": "behavior", "status": "pending"},
            {"id": "behavior:b", "kind": "behavior", "status": "pending"},
        ],
    }
    passing = build_report(
        task, {"behavior:a": {"verdict": "pass"}, "behavior:b": {"verdict": "pass"}}
    )
    assert passing["overall"] == "pass"
    failing = build_report(
        task, {"behavior:a": {"verdict": "pass"}, "behavior:b": {"verdict": "fail"}}
    )
    assert failing["overall"] == "fail"


def test_build_report_keeps_notes_and_rejects_bad_verdicts() -> None:
    task = {
        "id": "t1",
        "merge_commit": "tip",
        "title": "t",
        "items": [{"id": "behavior:a", "kind": "behavior", "status": "pending"}],
    }
    report = build_report(task, {"behavior:a": {"verdict": "pass", "notes": "ok in UI"}})
    assert report["items"][0]["notes"] == "ok in UI"
    assert report["items"][0]["verdict_by"] == "owner"
    with pytest.raises(ValueError, match="[Mm]issing verdict"):
        build_report(task, {})
    with pytest.raises(ValueError, match="pass or fail"):
        build_report(task, {"behavior:a": {"verdict": "maybe"}})


def test_build_report_carries_ancestor_proof() -> None:
    task = {
        "id": "t1",
        "merge_commit": "tip",
        "title": "t",
        "items": [
            {
                "id": "behavior:a",
                "kind": "behavior",
                "status": "auto-pass",
                "verdict_by": "ancestor",
                "proof": {"ancestor_commit": "old"},
                "tested_on": "old",
                "warning": "passed on old, code untouched since — not re-tested",
            }
        ],
    }
    report = build_report(task, {})
    assert report["overall"] == "pass"
    assert report["items"][0]["warning"].startswith("passed on old")
    assert report["items"][0]["tested_on"] == "old"


def test_promotion_verdict_is_per_merge_only() -> None:
    reports = [
        {"commit": "good", "overall": "pass", "built_utc": "2026-01-02T00:00:00+00:00"},
        {"commit": "bad", "overall": "fail", "built_utc": "2026-01-03T00:00:00+00:00"},
    ]
    assert promotion_verdict("good", reports).allowed is True
    assert promotion_verdict("bad", reports).allowed is False
    missing = promotion_verdict("other", reports)
    assert missing.allowed is False and "no E2E report" in missing.reason


def test_range_report_covers_merges_inside_span() -> None:
    order = {"base": 0, "mid": 1, "tip": 2}

    def runner(_root: str, *args: str) -> bytes:
        if args[:2] == ("merge-base", "--is-ancestor"):
            if order[args[2]] <= order[args[3]]:
                return b""
            raise RuntimeError("not ancestor")
        raise AssertionError(args)

    span = {"commit": "tip", "range_base": "base", "overall": "pass"}
    assert covers_range(span, "mid", ".", runner) is True
    assert covers_range(span, "tip", ".", runner) is True
    assert covers_range({**span, "overall": "fail"}, "mid", ".", runner) is False
    assert covers_range({"commit": "tip", "overall": "pass"}, "mid", ".", runner) is False
    assert uncovered_merges(["mid"], [span], ".", runner) == []
    assert uncovered_merges(["mid"], [], ".", runner) == ["mid"]


def test_guidance_attaches_what_how_expected() -> None:
    summaries = {
        "subjects": ["Add E2E tab"],
        "numstat": {"apps/workbench_dashboard/web/app.js": [120, 4]},
        "by_file": {"apps/workbench_dashboard/web/app.js": ["Add E2E tab"]},
    }
    checklist = generate_checklist(
        "tip", ["apps/workbench_dashboard/web/app.js"], summaries=summaries
    )
    dashboard = next(i for i in checklist["items"] if i["id"] == "behavior:dashboard")
    assert dashboard["what"] == ["Add E2E tab"]
    assert dashboard["churn"] == {"apps/workbench_dashboard/web/app.js": [120, 4]}
    assert len(dashboard["how"]) >= 2
    assert dashboard["expected"]
    assert dashboard["where"]


def test_regression_guidance_leads_with_framing() -> None:
    checklist = generate_checklist("tip", ["packages/ai_provider/a.py"], summaries={})
    regression = next(i for i in checklist["items"] if i["kind"] == "regression")
    assert regression["how"][0].startswith("Nothing here changed directly")


def test_change_summary_parses_log_and_numstat() -> None:
    def runner(_root: str, *args: str) -> bytes:
        if args[0] == "log":
            return b"SUBJECT:Add tab\n\napps/x.py\nSUBJECT:Fix tab\n\napps/x.py\n"
        return b"10\t2\tapps/x.py\n"

    summary = change_summary(".", "base", "tip", ["apps/x.py"], runner)
    assert summary["subjects"] == ["Add tab", "Fix tab"]
    assert summary["numstat"] == {"apps/x.py": [10, 2]}
    assert summary["by_file"] == {"apps/x.py": ["Add tab", "Fix tab"]}


def test_merge_listers_parse_git_output() -> None:
    def runner(_root: str, *args: str) -> bytes:
        if args[0] == "diff":
            return b"a.py\nb.py\n"
        return b"m1\nm2\n"

    assert merge_diff_files(".", "base", "tip", runner) == ["a.py", "b.py"]
    assert merges_between(".", "base", "tip", runner) == ["m1", "m2"]


def test_git_helpers_against_tmp_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=60)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True, timeout=60
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True, timeout=60)
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, timeout=60)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "one"], check=True, timeout=60)
    old = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    (tmp_path / "b.txt").write_text("two", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, timeout=60)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "two"], check=True, timeout=60)
    tip = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    root = str(tmp_path)
    assert is_ancestor(root, old, tip) is True
    assert is_ancestor(root, tip, old) is False
    proof = verify_no_diff(root, old, tip, ["a.txt"])
    assert proof is not None and proof["diff_bytes"] == 0
    assert verify_no_diff(root, old, tip, ["b.txt"]) is None
