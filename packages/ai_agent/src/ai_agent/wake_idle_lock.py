"""Dependency-free wake-idle lock protocol; keep compatible with wake_idle.interlock.

Both implementations lock byte zero of wake-idle.lock on Windows and use
flock on POSIX. Do not import the dashboard into the agent package.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

_LOCK = threading.RLock()


@contextmanager
def interlock(data_dir: Path):
    """Serialize admission and sleep commitment with the dashboard and sleep helper."""
    data_dir.mkdir(parents=True, exist_ok=True)
    with _LOCK, (data_dir / "wake-idle.lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            # Windows locks may extend beyond EOF. Initialize only while locked:
            # reading the locked byte before acquisition fails under contention.
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
