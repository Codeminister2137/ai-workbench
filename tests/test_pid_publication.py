"""Deterministic PID publication race coverage.

The ownership fixtures publish a descendant PID so that outer tests can verify
cleanup. A naive ``Path.write_text`` creates the target file before its contents
exist, so a reader that waits only for file existence can observe an empty or
partial PID. These tests exercise the same atomic write-and-rename publisher
used by the fixtures and prove readers cannot observe partial publication.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest


def _publish_pid(path: Path, pid: int) -> None:
    """Atomically publish ``pid`` at ``path``.

    The temporary file is renamed into place so readers never see a partially
    written file at the final path.
    """

    tmp = Path(str(path) + ".tmp")
    tmp.write_text(str(pid))
    tmp.replace(path)


def _read_pid(path: Path, timeout: float = 5.0) -> int:
    """Wait for a complete PID publication and return it as an int."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text().strip()
            if text:
                return int(text)
        time.sleep(0.001)
    raise FileNotFoundError("PID was not published in time")


def test_atomic_publication_hides_partial_write(tmp_path: Path) -> None:
    """A reader polling the target path never sees partial content.

    The writer intentionally delays the rename after writing the temporary file,
    giving the reader many opportunities to observe an in-progress publication.
    Because publication is atomic, the reader only sees the complete value.
    """

    pid_file = tmp_path / "child.pid"
    observed: dict[str, object] = {}

    def writer() -> None:
        tmp = Path(str(pid_file) + ".tmp")
        tmp.write_text("12345")
        # Hold the rename to expose any reader that polls only existence.
        time.sleep(0.2)
        tmp.replace(pid_file)

    def reader() -> None:
        try:
            observed["pid"] = _read_pid(pid_file, timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            observed["error"] = exc

    writer_thread = threading.Thread(target=writer)
    reader_thread = threading.Thread(target=reader)
    writer_thread.start()
    reader_thread.start()
    writer_thread.join()
    reader_thread.join()

    assert observed.get("pid") == 12345
    assert "error" not in observed


def test_reader_waits_for_content_not_just_existence(tmp_path: Path) -> None:
    """A file that exists but is empty does not satisfy the reader.

    This mirrors the original race where ``write_text`` created the target path
    before writing bytes. The reader must wait for non-empty, parseable content.
    """

    pid_file = tmp_path / "child.pid"
    pid_file.touch()
    ready = threading.Event()

    def writer() -> None:
        ready.wait()
        _publish_pid(pid_file, 99999)

    def reader() -> None:
        ready.set()
        observed = _read_pid(pid_file, timeout=2.0)
        assert observed == 99999

    writer_thread = threading.Thread(target=writer)
    reader_thread = threading.Thread(target=reader)
    writer_thread.start()
    reader_thread.start()
    writer_thread.join()
    reader_thread.join()


def test_publish_pid_overwrites_whitespace_stale_file(tmp_path: Path) -> None:
    """Publishing a PID atomically replaces a stale file containing only whitespace."""

    pid_file = tmp_path / "child.pid"
    pid_file.write_text("   \n")
    _publish_pid(pid_file, 123)
    assert _read_pid(pid_file) == 123


def test_publish_pid_overwrites_stale_file(tmp_path: Path) -> None:
    """Publishing a new PID replaces any existing stale publication atomically."""

    pid_file = tmp_path / "child.pid"
    pid_file.write_text("stale")
    _publish_pid(pid_file, 42)
    assert _read_pid(pid_file) == 42


def test_reader_times_out_cleanly_when_pid_never_appears(tmp_path: Path) -> None:
    """A publication that never happens fails with a clear error, not a hang.

    Cleanup code waits for the descendant's PID before terminating it; when the
    child dies before publishing, the wait must give up after its deadline
    instead of blocking forever or returning a bogus PID.
    """

    pid_file = tmp_path / "child.pid"
    started = time.monotonic()
    with pytest.raises(FileNotFoundError, match="PID was not published in time"):
        _read_pid(pid_file, timeout=0.2)
    elapsed = time.monotonic() - started

    assert 0.2 <= elapsed < 5.0
    assert not pid_file.exists()


def test_publishing_same_pid_twice_is_idempotent(tmp_path: Path) -> None:
    """Republishing an identical PID leaves the same readable state behind.

    A retried publication must not corrupt the value, leave the temporary file
    behind, or make the reader observe a partial write.
    """

    pid_file = tmp_path / "child.pid"
    _publish_pid(pid_file, 4242)
    first = pid_file.read_text()

    _publish_pid(pid_file, 4242)
    second = pid_file.read_text()

    assert first == second == "4242"
    assert _read_pid(pid_file) == 4242
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["child.pid"]
