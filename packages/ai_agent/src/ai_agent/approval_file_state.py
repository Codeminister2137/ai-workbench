"""Local file-state evidence for remote approval, without retaining file content."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from pathlib import Path

from ai_agent.tools.credential_paths import is_credential_path


def capture_file_state(
    workspace: Path, paths: tuple[str, ...], check_active: Callable[[], object]
) -> str:
    """Hash declared targets and path identities; refuse unsafe/unstable reads.

    This detects state differences across an approval wait, not every historical
    mutation, arbitrary command inputs, or a race after the callback returns.
    """
    root = workspace.resolve()
    if not paths or any(not isinstance(raw, str) or not raw.strip() for raw in paths):
        raise ValueError("No file approval targets declared")
    evidence = []
    for raw in sorted(set(paths)):
        check_active()
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Invalid file approval target")
        requested = Path(os.path.abspath(root / raw))
        target = requested.resolve()
        if (
            not requested.is_relative_to(root)
            or not target.is_relative_to(root)
            or is_credential_path(requested)
            or is_credential_path(target)
        ):
            raise ValueError("Unsafe file approval target")
        ancestors = []
        parent = requested.parent
        while parent.is_relative_to(root):
            check_active()
            try:
                info = parent.lstat()
            except FileNotFoundError:
                identity = None
            else:
                if not parent.is_dir():
                    raise ValueError("Invalid file approval parent")
                identity = (info.st_dev, info.st_ino, info.st_mode, str(parent.resolve()))
            ancestors.append((str(parent), identity))
            if parent == root:
                break
            parent = parent.parent
        try:
            before = target.stat()
        except FileNotFoundError:
            # Broken links/special nodes must not be treated as absent files.
            if requested.is_symlink() or requested.exists():
                raise ValueError("Invalid absent file approval target") from None
            file_state = None
        else:
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("File approval target must be a regular file")
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                if stream_stat(stream.fileno()) != signature(before):
                    raise ValueError("File changed while capturing approval state")
                while chunk := stream.read(65536):
                    check_active()
                    digest.update(chunk)
                if stream_stat(stream.fileno()) != signature(before):
                    raise ValueError("File changed while capturing approval state")
            if signature(target.stat()) != signature(before) or requested.resolve() != target:
                raise ValueError("File changed while capturing approval state")
            file_state = (signature(before), digest.hexdigest())
        evidence.append((raw, str(target), ancestors, file_state))
    check_active()
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()


def signature(info: os.stat_result) -> tuple[int, ...]:
    # Windows path stat and handle fstat can disagree on ctime after a write.
    # Content/identity/mode/size/mtime are the compared approval state.
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
    )


def stream_stat(descriptor: int) -> tuple[int, ...]:
    return signature(os.fstat(descriptor))
