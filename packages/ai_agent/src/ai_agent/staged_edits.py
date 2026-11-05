"""Staged project-file edits behind an exact-match work-root allowlist.

Adapted from the frozen operator ``ProjectOperator`` mechanics: a run stages
file contents inside one registered project root, the owner reviews the
staged diff, and approval re-verifies every digest before anything is
applied to the root. Nothing is written to the root until approve-and-apply.

Provider-neutral by construction: this module touches only the local
filesystem and never calls a model. Staged records live on the dashboard run
record (``run["staged"]``); the agent loop does NOT stage here yet — that
wiring is a later integration, and this module is the seam it will use.

Approval semantics: project approvals record ``checks: "none"`` by design.
No automated validation runs over staged project files; sample validation
is skipped for project approvals on purpose and the owner is the reviewer.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_DENY_BASENAMES = frozenset(
    {"credentials.json", "secrets.json", "id_rsa", "id_ed25519", "id_ecdsa"}
)
PROJECT_DENY_SUFFIXES = (".pem", ".key")
MAX_PROJECT_PATH_CHARS = 512
MAX_STAGED_BYTES = 32_768
ROOT_ID_CHARS = 12


class StagedEditError(ValueError):
    """A staged-edit refusal safe to report to the dashboard caller."""


class StagedConflictError(StagedEditError):
    """Staged or on-disk bytes changed since review; approve must fail shut."""


def digest(value: str | bytes) -> str:
    """Return the sha256 hex digest of one text or byte value."""
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def root_id(root: Path) -> str:
    """Return the stable short id for one resolved work root."""
    return digest(os.path.realpath(root))[:ROOT_ID_CHARS]


def resolve_project_path(root: Path, rel: str) -> Path:
    """Resolve ``rel`` inside ``root`` for project-file tasks, or refuse it.

    Every segment must be an explicit plain name: absolute paths, drive
    letters, parent references, dot-segments, hidden names and
    secret-looking basenames are refused before any filesystem access. The
    resolved path must stay inside ``root`` and neither it nor any
    directory between ``root`` and its parent may be a link or junction.
    """
    root = Path(os.path.realpath(root))
    if not isinstance(rel, str) or not rel or len(rel) > MAX_PROJECT_PATH_CHARS:
        raise StagedEditError("Project path is not admitted")
    if "\\" in rel:
        raise StagedEditError("Project path is not admitted")
    candidate = Path(rel)
    if candidate.is_absolute() or ":" in rel:
        raise StagedEditError("Project path is not admitted")
    # Split textually: Path parsing would silently drop "." segments.
    segments = rel.split("/")
    if not segments:
        raise StagedEditError("Project path is not admitted")
    for segment in segments:
        if segment in {"", ".", ".."} or segment.startswith(".") or segment.endswith((".", " ")):
            raise StagedEditError("Project path is not admitted")
    lowered = segments[-1].lower()
    if lowered in PROJECT_DENY_BASENAMES or lowered.endswith(PROJECT_DENY_SUFFIXES):
        raise StagedEditError("Project path is not admitted")
    full = Path(os.path.realpath(root / candidate))
    if full != root and root not in full.parents:
        raise StagedEditError("Project path escapes the registered root")
    for part in full.relative_to(root).parts:
        if part.startswith("."):
            raise StagedEditError("Project path is not admitted")
    resolved_leaf = full.name.lower()
    if resolved_leaf in PROJECT_DENY_BASENAMES or resolved_leaf.endswith(PROJECT_DENY_SUFFIXES):
        raise StagedEditError("Project path is not admitted")
    node = full if full.is_dir() else full.parent
    while True:
        if node.is_symlink() or node.is_junction():
            raise StagedEditError("Linked project path is forbidden")
        if node == root:
            break
        node = node.parent
    if full.exists() and (full.is_symlink() or full.is_junction()):
        raise StagedEditError("Linked project path is forbidden")
    return full


def _refuses_overlap(root: Path, protected: Path) -> bool:
    """True when ``root`` equals, contains, or sits inside ``protected``."""
    return root == protected or root in protected.parents or protected in root.parents


@dataclass(frozen=True, slots=True)
class ProjectRootEntry:
    """One registered work root for the dashboard registry view."""

    id: str
    path: str
    display_name: str


class ProjectRoots:
    """Exact-match allowlist of project work roots (fail-closed).

    An empty allowlist means NO project access. Selection is exact-match
    only: a ref must equal a registered root id or resolve to exactly a
    registered root path — no fuzzy or substring matching.
    """

    def __init__(
        self, roots: Iterable[str | Path], *, protected_dirs: Iterable[str | Path] = ()
    ) -> None:
        protected = [Path(entry).resolve() for entry in protected_dirs]
        resolved: list[Path] = []
        for candidate in roots:
            path = Path(candidate).resolve()
            if not path.is_dir():
                raise StagedEditError("Work root is not a directory")
            if path == path.parent:
                raise StagedEditError("Work root must not be a filesystem root")
            for guarded in protected:
                if _refuses_overlap(path, guarded):
                    raise StagedEditError("Work root must not overlap the runtime store")
            resolved.append(path)
        self._roots = tuple(dict.fromkeys(resolved))

    def __len__(self) -> int:
        return len(self._roots)

    def entries(self) -> list[ProjectRootEntry]:
        """List registered roots as stable registry entries."""
        return [
            ProjectRootEntry(id=root_id(root), path=str(root), display_name=root.name)
            for root in self._roots
        ]

    def select(self, ref: str | None) -> Path:
        """Return the registered root matching ``ref`` (id or path), or refuse."""
        if not isinstance(ref, str) or not ref:
            raise StagedEditError("A registered project root is required")
        for root in self._roots:
            if ref == root_id(root):
                return root
        try:
            candidate = Path(ref).resolve()
        except OSError:
            raise StagedEditError("Unknown work root") from None
        for root in self._roots:
            if candidate == root:
                return root
        raise StagedEditError("Unknown work root")


def read_project_file(root: Path, rel: str) -> str:
    """Read one admitted UTF-8 text file from a registered project root."""
    path = resolve_project_path(root, rel)
    if not path.is_file():
        raise StagedEditError("Project path is not a readable file")
    if path.stat().st_size > MAX_STAGED_BYTES:
        raise StagedEditError("Project file exceeds allowed size")
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise StagedEditError("Project file is not decodable text") from None


def stage_file(root: Path, relpath: str, content: str) -> dict:
    """Build one staged record for ``content`` at ``relpath`` under ``root``.

    The path is validated exactly as at apply time and the on-disk base is
    snapshotted as ``base_digest`` (None for a new file). The record carries
    its own ``content`` so the run record stays the staging area; no disk
    write happens here.
    """
    resolve_project_path(root, relpath)
    if not isinstance(content, str) or len(content.encode()) > MAX_STAGED_BYTES:
        raise StagedEditError("Invalid staged size/type")
    try:
        base_digest: str | None = digest(read_project_file(root, relpath))
    except StagedEditError:
        if resolve_project_path(root, relpath).is_file():
            raise
        base_digest = None
    return {
        "relpath": relpath,
        "digest": digest(content),
        "base_digest": base_digest,
        "content": content,
    }


def staged_diff(base: str | None, staged: str, *, relpath: str) -> str:
    """Render one staged file as unified-diff text for owner review."""
    base_lines = (base or "").splitlines(keepends=True)
    staged_lines = staged.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            base_lines,
            staged_lines,
            fromfile="base/" + relpath,
            tofile="candidate/" + relpath,
        )
    )


def _coerce_records(staged: Iterable[Mapping]) -> list[dict]:
    records: list[dict] = []
    for entry in staged:
        if not isinstance(entry, Mapping):
            raise StagedEditError("Staged record is malformed")
        relpath = entry.get("relpath")
        content = entry.get("content")
        expected = entry.get("digest")
        if not isinstance(relpath, str) or not isinstance(content, str):
            raise StagedEditError("Staged record is malformed")
        if not isinstance(expected, str) or digest(content) != expected:
            raise StagedConflictError("Reviewed staged files changed")
        records.append(
            {
                "relpath": relpath,
                "digest": expected,
                "base_digest": entry.get("base_digest"),
                "content": content,
            }
        )
    return records


def verify_staged(roots: ProjectRoots, root_ref: str, staged: Iterable[Mapping]) -> list[dict]:
    """Re-check roots and digests for staged records without applying them.

    This is the revalidate entry point: it selects the still-registered
    root, re-validates every path, re-compares every staged digest, and
    re-reads every on-disk base. Any drift raises ``StagedConflictError``
    and nothing is applied.
    """
    root = roots.select(root_ref)
    records = _coerce_records(staged)
    if not records:
        raise StagedEditError("No staged project changes")
    for record in records:
        resolve_project_path(root, record["relpath"])
        try:
            current_base: str | None = digest(read_project_file(root, record["relpath"]))
        except StagedEditError:
            if resolve_project_path(root, record["relpath"]).is_file():
                raise
            current_base = None
        if current_base != record["base_digest"]:
            raise StagedConflictError("Reviewed project files changed")
    return records


def approve_staged(roots: ProjectRoots, root_ref: str, staged: Iterable[Mapping]) -> dict:
    """Approve staged records after re-verifying roots and digests.

    Project approvals record ``checks: "none"``: no automated validation
    runs over project files and sample validation is skipped by design —
    the owner reviewing the staged diff is the check.
    """
    records = verify_staged(roots, root_ref, staged)
    return {
        "checks": "none",
        "files": [{"relpath": record["relpath"], "digest": record["digest"]} for record in records],
    }


def apply_staged(root: Path, staged: Iterable[Mapping]) -> list[dict]:
    """Apply verified staged records to ``root`` with atomic per-file writes.

    Each file lands via tmp+rename; parent directories are created inside
    the root only (containment is re-checked after creation, before the
    rename). Callers must run :func:`verify_staged` first — this function
    re-validates paths and digests but does not re-check the allowlist.
    """
    root = Path(root).resolve()
    records = _coerce_records(staged)
    applied: list[dict] = []
    for record in records:
        destination = resolve_project_path(root, record["relpath"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Re-resolve after mkdir: a raced link must still refuse, never write.
        destination = resolve_project_path(root, record["relpath"])
        if destination.exists() and not destination.is_file():
            raise StagedEditError("Staged path is not a plain file")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(record["content"].encode("utf-8"))
            resolve_project_path(root, record["relpath"])
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        applied.append({"relpath": record["relpath"], "digest": record["digest"]})
    return applied


def review_staged(root: Path, staged: Iterable[Mapping]) -> list[dict]:
    """Render staged records as per-file diffs against the current on-disk base."""
    root = Path(root).resolve()
    views: list[dict] = []
    for record in _coerce_records(staged):
        relpath = record["relpath"]
        resolve_project_path(root, relpath)
        try:
            base: str | None = read_project_file(root, relpath)
        except StagedEditError:
            if resolve_project_path(root, relpath).is_file():
                raise
            base = None
        views.append(
            {
                "relpath": relpath,
                "digest": record["digest"],
                "base_digest": record["base_digest"],
                "diff": staged_diff(base, record["content"], relpath=relpath),
            }
        )
    return views
