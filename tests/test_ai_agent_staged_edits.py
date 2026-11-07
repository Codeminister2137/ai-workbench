"""Staged project-file edits: allowlist, path refusal, approve/apply."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_agent.staged_edits import (
    MAX_STAGED_BYTES,
    ProjectRoots,
    StagedConflictError,
    StagedEditError,
    apply_staged,
    approve_staged,
    digest,
    resolve_project_path,
    review_staged,
    root_id,
    stage_file,
    staged_diff,
    staged_diffstat,
    verify_staged,
)


def _roots(*dirs: Path, protected: tuple[Path, ...] = ()) -> ProjectRoots:
    return ProjectRoots([str(entry) for entry in dirs], protected_dirs=protected)


def _try_symlink(link: Path, target: Path, *, is_dir: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=is_dir)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314 or isinstance(error, PermissionError):
            pytest.skip("Host does not permit creating test symlinks")
        raise


# --- allowlist ---


def test_empty_allowlist_refuses_everything(tmp_path: Path) -> None:
    roots = _roots()
    assert len(roots) == 0
    assert roots.entries() == []
    with pytest.raises(StagedEditError):
        roots.select(str(tmp_path))
    with pytest.raises(StagedEditError):
        roots.select(None)


def test_select_accepts_exact_path_and_stable_id(tmp_path: Path) -> None:
    project = tmp_path / "client-a"
    project.mkdir()
    roots = _roots(project)
    assert roots.select(str(project)) == project.resolve()
    (entry,) = roots.entries()
    assert entry.display_name == "client-a"
    assert entry.path == str(project.resolve())
    assert roots.select(entry.id) == project.resolve()
    # Stable across rebuilds: id derives from the resolved path only.
    (rebuilt,) = _roots(project).entries()
    assert rebuilt.id == entry.id
    assert root_id(project) == entry.id


def test_select_refuses_fuzzy_matches(tmp_path: Path) -> None:
    project = tmp_path / "client-a"
    project.mkdir()
    sibling = tmp_path / "client-ab"
    sibling.mkdir()
    roots = _roots(project)
    with pytest.raises(StagedEditError):
        roots.select("client-a")  # bare name, not a registered root
    with pytest.raises(StagedEditError):
        roots.select(str(sibling))  # sibling prefix, not exact
    with pytest.raises(StagedEditError):
        roots.select(str(tmp_path))  # parent dir, not exact
    with pytest.raises(StagedEditError):
        roots.select(str(project / "sub"))  # child dir, not exact
    with pytest.raises(StagedEditError):
        roots.select("")
    with pytest.raises(StagedEditError):
        roots.select("deadbeefcafe")  # unknown id


def test_allowlist_dedupes_and_rejects_non_directories(tmp_path: Path) -> None:
    project = tmp_path / "client-a"
    project.mkdir()
    assert len(_roots(project, project)) == 1
    with pytest.raises(StagedEditError, match="not a directory"):
        _roots(tmp_path / "missing")
    leaf = tmp_path / "file.txt"
    leaf.write_text("x", encoding="utf-8")
    with pytest.raises(StagedEditError, match="not a directory"):
        _roots(leaf)


def test_overlap_guard_refuses_runtime_dirs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "runs").mkdir()
    with pytest.raises(StagedEditError, match="overlap"):
        _roots(data_dir, protected=(data_dir,))  # equal
    with pytest.raises(StagedEditError, match="overlap"):
        _roots(tmp_path, protected=(data_dir,))  # contains the data dir
    with pytest.raises(StagedEditError, match="overlap"):
        _roots(data_dir / "runs", protected=(data_dir,))  # inside the data dir
    venv = tmp_path / ".venv"
    venv.mkdir()
    with pytest.raises(StagedEditError, match="overlap"):
        _roots(tmp_path, protected=(venv,))


def test_filesystem_root_is_refused(tmp_path: Path) -> None:
    anchor = Path(tmp_path.anchor)
    with pytest.raises(StagedEditError):
        _roots(anchor)


def test_unregistered_root_fails_on_reselect(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    ref = str(first)
    assert _roots(first, second).select(ref) == first.resolve()
    with pytest.raises(StagedEditError, match="Unknown work root"):
        _roots(second).select(ref)


# --- path resolution ---


def test_resolve_accepts_nested_plain_paths(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    assert resolve_project_path(root, "src/main.py") == (root / "src" / "main.py").resolve()


@pytest.mark.parametrize(
    "rel",
    [
        "",
        "../escape.txt",
        "sub/../../escape.txt",
        "/absolute.txt",
        "C:/win.txt",
        "C:\\win.txt",
        "back\\slash.txt",
        "./dot.txt",
        "sub/./dot.txt",
        "sub/../up.txt",
        ".hidden",
        "sub/.hidden",
        "trailing.",
        "trailing ",
        "sub/trailing. ",
        "credentials.json",
        "sub/SeCrEtS.json",
        "id_rsa",
        "sub/id_ed25519",
        "key.pem",
        "sub/key.KEY",
        "a" * 513,
    ],
)
def test_resolve_refuses_hostile_names(tmp_path: Path, rel: str) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(StagedEditError):
        resolve_project_path(root, rel)


def test_resolve_refuses_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = root / "alias.txt"
    _try_symlink(link, outside)
    with pytest.raises(StagedEditError):
        resolve_project_path(root, "alias.txt")


def test_resolve_refuses_symlink_in_parent_chain(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    link = root / "linked"
    _try_symlink(link, real, is_dir=True)
    (real / "inner.txt").write_text("x", encoding="utf-8")
    with pytest.raises(StagedEditError):
        resolve_project_path(root, "linked/inner.txt")


# --- stage / diff / review ---


def test_stage_file_snapshots_base_digest(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    # Bytes, not write_text: digests are byte-exact, text mode would add \r\n.
    (root / "main.py").write_bytes(b"old\n")
    record = stage_file(root, "main.py", "new\n")
    assert record["relpath"] == "main.py"
    assert record["digest"] == digest("new\n")
    assert record["base_digest"] == digest("old\n")
    assert record["content"] == "new\n"
    fresh = stage_file(root, "added.py", "hello\n")
    assert fresh["base_digest"] is None
    # Staging never writes to the root.
    assert not (root / "added.py").exists()
    assert (root / "main.py").read_text(encoding="utf-8") == "old\n"


def test_stage_file_validates_path_and_size(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(StagedEditError):
        stage_file(root, "../escape.txt", "x")
    with pytest.raises(StagedEditError):
        stage_file(root, "ok.txt", "x" * (MAX_STAGED_BYTES + 1))


def test_staged_diff_renders_unified_text() -> None:
    text = staged_diff("old\n", "new\n", relpath="main.py")
    assert "--- base/main.py" in text
    assert "+++ candidate/main.py" in text
    assert "-old" in text
    assert "+new" in text


def test_staged_diffstat_counts_added_removed() -> None:
    assert staged_diffstat("a\nb\n", "a\nc\nd\n") == {"added": 2, "removed": 1}
    assert staged_diffstat("a\nb\n", "a\n") == {"added": 0, "removed": 1}
    assert staged_diffstat(None, "hi\n") == {"added": 1, "removed": 0}
    assert staged_diffstat("same\n", "same\n") == {"added": 0, "removed": 0}


def test_review_staged_includes_diffstat(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("old\n", encoding="utf-8")
    staged = [stage_file(root, "main.py", "new\n"), stage_file(root, "added.py", "hi\n")]
    views = review_staged(root, staged)
    assert views[0]["diffstat"] == {"added": 1, "removed": 1}
    assert views[1]["diffstat"] == {"added": 1, "removed": 0}


def test_review_staged_lists_per_file_diffs(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("old\n", encoding="utf-8")
    staged = [stage_file(root, "main.py", "new\n"), stage_file(root, "added.py", "hi\n")]
    views = review_staged(root, staged)
    assert [view["relpath"] for view in views] == ["main.py", "added.py"]
    assert "-old" in views[0]["diff"] and "+new" in views[0]["diff"]
    assert "+hi" in views[1]["diff"]


# --- approve / revalidate / apply ---


def test_approve_records_checks_none(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("old\n", encoding="utf-8")
    roots = _roots(root)
    staged = [stage_file(root, "main.py", "new\n")]
    approval = approve_staged(roots, str(root), staged)
    assert approval["checks"] == "none"
    assert approval["files"] == [{"relpath": "main.py", "digest": digest("new\n")}]


def test_approve_refuses_tampered_staged_content(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    roots = _roots(root)
    staged = [stage_file(root, "main.py", "new\n")]
    staged[0]["content"] = "evil\n"
    with pytest.raises(StagedConflictError, match="staged files changed"):
        approve_staged(roots, str(root), staged)
    assert not (root / "main.py").exists()


def test_approve_refuses_moved_base(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("old\n", encoding="utf-8")
    roots = _roots(root)
    staged = [stage_file(root, "main.py", "new\n")]
    (root / "main.py").write_text("someone else\n", encoding="utf-8")
    with pytest.raises(StagedConflictError, match="project files changed"):
        approve_staged(roots, str(root), staged)
    assert (root / "main.py").read_text(encoding="utf-8") == "someone else\n"


def test_approve_refuses_deleted_base(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("old\n", encoding="utf-8")
    roots = _roots(root)
    staged = [stage_file(root, "main.py", "new\n")]
    (root / "main.py").unlink()
    with pytest.raises(StagedConflictError, match="project files changed"):
        approve_staged(roots, str(root), staged)


def test_approve_refuses_unknown_and_unregistered_roots(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    staged = [stage_file(root, "main.py", "new\n")]
    with pytest.raises(StagedEditError, match="Unknown work root"):
        approve_staged(_roots(root), "nope", staged)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(StagedEditError, match="Unknown work root"):
        approve_staged(_roots(other), str(root), staged)


def test_approve_refuses_empty_staged(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(StagedEditError, match="No staged project changes"):
        approve_staged(_roots(root), str(root), [])


def test_verify_staged_is_the_revalidate_entry_point(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("old\n", encoding="utf-8")
    roots = _roots(root)
    staged = [stage_file(root, "main.py", "new\n")]
    verified = verify_staged(roots, str(root), staged)
    assert [record["relpath"] for record in verified] == ["main.py"]
    (root / "main.py").write_text("drift\n", encoding="utf-8")
    with pytest.raises(StagedConflictError):
        verify_staged(roots, str(root), staged)


def test_apply_writes_atomically_and_builds_parents(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("old\n", encoding="utf-8")
    staged = [
        stage_file(root, "main.py", "new\n"),
        stage_file(root, "nested/deep/added.py", "hi\n"),
    ]
    applied = apply_staged(root, staged)
    assert [entry["relpath"] for entry in applied] == ["main.py", "nested/deep/added.py"]
    assert (root / "main.py").read_text(encoding="utf-8") == "new\n"
    assert (root / "nested" / "deep" / "added.py").read_text(encoding="utf-8") == "hi\n"
    leftovers = [path for path in root.rglob("*") if "tmp" in path.name]
    assert leftovers == []


def test_apply_refuses_directory_destination(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "adir").mkdir()
    staged = [
        {
            "relpath": "adir",
            "digest": digest("x"),
            "base_digest": None,
            "content": "x",
        }
    ]
    with pytest.raises(StagedEditError):
        apply_staged(root, staged)
    assert (root / "adir").is_dir()
