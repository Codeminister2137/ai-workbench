"""Live proof for the Docker launcher (manual, needs the engine).

Runs a small guest probe through ``docker_launcher.launch`` against the
pinned image: workspace write, read-only root refusal, env hygiene.
Writes evidence and refuses to pass on any deviation. Never touches
the real repo, credentials, or shared Git metadata.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "workbench_dashboard"))

from docker_launcher import DockerRunSpec, launch  # noqa: E402

GUEST = "\n".join(
    [
        "import json, os",
        "findings = {}",
        "open('/workspace/probe.txt', 'w').write('ok')",
        "findings['write'] = open('/workspace/probe.txt').read() == 'ok'",
        "try:",
        "    open('/host-sentinel', 'w')",
        "except OSError:",
        "    findings['root_readonly'] = True",
        "else:",
        "    findings['root_readonly'] = False",
        "findings['no_creds'] = not [k for k in os.environ if 'TOKEN' in k.upper()]",
        "open('/result/result.json', 'w').write(json.dumps({'findings': findings}))",
    ]
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--image", default=None, help="Image ref (default: pinned probe digest).")
    parser.add_argument(
        "--smoke-argv",
        nargs=argparse.REMAINDER,
        default=None,
        help="Optional argv to run instead of the guest probe (skips finding asserts).",
    )
    args = parser.parse_args(argv)
    if args.evidence_dir.exists():
        parser.error("evidence dir already exists; preserve consumed runs")
    with tempfile.TemporaryDirectory(prefix="launcher-src-") as src:
        Path(src, "hello.txt").write_text("seed\n", encoding="utf-8")
        smoke = list(args.smoke_argv) if args.smoke_argv else None
        if smoke and smoke[0] == "--":
            smoke = smoke[1:]
        spec = DockerRunSpec(
            run_id="launcher-probe",
            argv=tuple(smoke) if smoke else ("python", "-c", GUEST),
            workspace_src=Path(src),
            timeout_seconds=120.0,
            **({"image": args.image} if args.image else {}),
        )
        result = launch(spec)
    args.evidence_dir.mkdir(parents=True)
    evidence = {
        "ok": result.ok,
        "exit_code": result.exit_code,
        "elapsed_seconds": result.elapsed_seconds,
        "result": result.result,
        "error": result.error,
    }
    (args.evidence_dir / "launcher-proof.json").write_text(
        json.dumps(evidence, indent=1), encoding="utf-8"
    )
    print(json.dumps(evidence, indent=1)[:800])
    if smoke:
        # Smoke commands print to stdout instead of result.json;
        # a clean guest exit is the pass criterion here.
        return 0 if result.exit_code == 0 else 1
    findings = (result.result or {}).get("findings", {})
    if not (
        result.ok
        and findings.get("write") is True
        and findings.get("root_readonly") is True
        and findings.get("no_creds") is True
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
