"""Local clean-source CI design probe, with shared dependencies explicitly disclosed."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path

root = Path.cwd()
out = root / ".tmp/health-48679817"
archive = out / "checkout.tar"
checkout = out / "clean-checkout"
checkout.mkdir(exist_ok=False)
with archive.open("xb") as stream:
    subprocess.run(["git", "archive", "HEAD"], stdout=stream, check=True)
with tarfile.open(archive) as source:
    source.extractall(checkout, filter="data")
spec = importlib.util.spec_from_file_location("clean_suites", checkout / "scripts/run-tests.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
membership = module.suite_files(checkout)
command = [
    sys.executable,
    "-m",
    "pytest",
    "tests/test_document_status.py",
    "tests/test_test_suites.py",
    "-q",
    "-n",
    "0",
]
started = time.monotonic()
with (out / "clean-checkout.log").open("x", encoding="utf-8") as stream:
    result = subprocess.run(
        command,
        cwd=checkout,
        env=module.test_environment(),
        stdout=stream,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
record = {
    "command": command,
    "exit": result.returncode,
    "seconds": round(time.monotonic() - started, 3),
    "private_plans_present": (checkout / "docs/plans").exists(),
    "dotenv_present": (checkout / ".env").exists(),
    "modules_per_group": {k: len(v) for k, v in membership.items()},
    "limitations": "Tracked HEAD archive, no Git metadata; shared existing venv; no fresh dependency install, hosted run, or full clean-checkout suite.",
}
with (out / "clean-checkout.json").open("x", encoding="utf-8") as stream:
    json.dump(record, stream, indent=2)
print(json.dumps(record, indent=2))
