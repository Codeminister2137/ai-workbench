"""Dual-root document library: public tracked docs plus private local files.

Roots (relative to the repo root):

- ``library`` (``docs/library/``, tracked): portfolio-safe documents.
- ``plans`` (``docs/plans/``, gitignored): existing private plans and company
  research, surfaced read-only so nothing moves and no link breaks.
- ``private`` (``docs/library-private/``, gitignored): company-sensitive
  default for new research (pricing, clients, market deliberations).

Markdown files may carry a small front-matter block (title, tags, project,
created); anything else lists by filename. Missing roots scan as empty.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOTS = {
    "library": ("docs/library", "public"),
    "plans": ("docs/plans", "private"),
    "private": ("docs/library-private", "private"),
}

MAX_TEXT_BYTES = 100_000
MAX_ENTRIES = 1000


@dataclass(slots=True)
class DocumentEntry:
    """One listed file with its parsed front-matter and root provenance."""

    id: str
    root: str
    relpath: str
    title: str
    tags: tuple[str, ...]
    project: str | None
    size: int
    modified_utc: str
    sensitivity: str
    renderable: bool
    archived: bool


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split an optional ``---`` block into (fields, body).

    Dependency-free: only flat ``key: value`` lines are read; anything else
    is ignored and the whole file stays the body.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    lines = text.splitlines(keepends=True)
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            end = index
            break
    if end is None:
        return {}, text
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip("'\"")
        if key and value:
            fields[key] = value
    return fields, "".join(lines[end + 1 :])


def _split_tags(raw: str) -> tuple[str, ...]:
    cleaned = raw.strip().strip("[]")
    return tuple(part.strip() for part in cleaned.split(",") if part.strip())


class DocumentLibrary:
    """Scan and serve library files; ids never escape their root."""

    def __init__(self, repo_root: Path, *, roots: dict[str, Path] | None = None) -> None:
        self.repo_root = repo_root
        if roots is None:
            self._roots = {
                name: (repo_root / rel, sensitivity) for name, (rel, sensitivity) in ROOTS.items()
            }
        else:
            self._roots = {
                name: (path, ROOTS.get(name, ("", "private"))[1]) for name, path in roots.items()
            }

    def list_documents(self) -> list[dict]:
        """List every file under every present root, newest-first."""
        entries: list[DocumentEntry] = []
        for name, (root_dir, _sensitivity) in self._roots.items():
            if not root_dir.is_dir():
                continue
            for path in sorted(root_dir.rglob("*")):
                if not path.is_file() or _is_hidden(path, root_dir):
                    continue
                entries.append(self._describe(name, root_dir, path))
                if len(entries) >= MAX_ENTRIES:
                    break
        entries.sort(key=lambda entry: entry.modified_utc, reverse=True)
        return [self._to_dict(entry) for entry in entries[:MAX_ENTRIES]]

    def get(self, doc_id: str) -> DocumentEntry:
        """Resolve one ``{root}/{relpath}`` id, refusing escapes and misses."""
        root, _, relpath = doc_id.partition("/")
        if root not in self._roots or not relpath:
            raise KeyError(f"Unknown document: {doc_id}")
        if "\\" in relpath or relpath.startswith("/"):
            raise ValueError(f"Invalid document id: {doc_id}")
        root_dir = self._roots[root][0].resolve()
        candidate = (self._roots[root][0] / relpath).resolve()
        if candidate != root_dir and root_dir not in candidate.parents:
            raise ValueError(f"Invalid document id: {doc_id}")
        if not candidate.is_file() or _is_hidden(candidate, self._roots[root][0]):
            raise KeyError(f"Unknown document: {doc_id}")
        return self._describe(root, self._roots[root][0], candidate)

    def read_text(self, doc_id: str) -> tuple[str, bool]:
        """Return (body-without-front-matter, truncated) for markdown docs."""
        entry = self.get(doc_id)
        if not entry.renderable:
            raise ValueError(f"Document is not renderable: {doc_id}")
        path = (self._roots[entry.root][0] / entry.relpath).resolve()
        raw = path.read_bytes()
        truncated = len(raw) > MAX_TEXT_BYTES
        text = raw[:MAX_TEXT_BYTES].decode("utf-8", errors="replace").replace("\r\n", "\n")
        _fields, body = parse_front_matter(text)
        return body, truncated

    def read_bytes(self, doc_id: str) -> tuple[bytes, str]:
        """Return (bytes, content-type) for one-click open/download."""
        entry = self.get(doc_id)
        path = (self._roots[entry.root][0] / entry.relpath).resolve()
        content_type, _encoding = mimetypes.guess_type(path.name)
        return path.read_bytes(), content_type or "application/octet-stream"

    def _describe(self, root: str, root_dir: Path, path: Path) -> DocumentEntry:
        relpath = path.relative_to(root_dir).as_posix()
        title = path.stem
        tags: tuple[str, ...] = ()
        project = None
        archived = False
        if path.suffix.lower() == ".md":
            try:
                fields, _body = parse_front_matter(
                    path.read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                fields = {}
            title = fields.get("title", path.stem)
            if "tags" in fields:
                tags = _split_tags(fields["tags"])
            project = fields.get("project")
            archived = fields.get("archived", "").strip().lower() in ("true", "yes", "1")
        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        return DocumentEntry(
            id=f"{root}/{relpath}",
            root=root,
            relpath=relpath,
            title=title,
            tags=tags,
            project=project,
            size=path.stat().st_size,
            modified_utc=modified,
            sensitivity=self._roots[root][1],
            renderable=path.suffix.lower() == ".md",
            archived=archived,
        )

    @staticmethod
    def _to_dict(entry: DocumentEntry) -> dict:
        return {
            "id": entry.id,
            "root": entry.root,
            "relpath": entry.relpath,
            "title": entry.title,
            "tags": list(entry.tags),
            "project": entry.project,
            "size": entry.size,
            "modified_utc": entry.modified_utc,
            "sensitivity": entry.sensitivity,
            "renderable": entry.renderable,
            "archived": entry.archived,
        }


def _is_hidden(path: Path, root_dir: Path) -> bool:
    try:
        rel = path.relative_to(root_dir)
    except ValueError:
        return True
    return any(part.startswith(".") for part in rel.parts)


__all__ = ["ROOTS", "DocumentEntry", "DocumentLibrary", "parse_front_matter"]
