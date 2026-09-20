from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from ai_provider import (
    LocalOllamaModel,
    OllamaPullConstraints,
    OllamaPullProgress,
    list_local_ollama_models,
    pull_ollama_model,
    show_ollama_model,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage local Ollama models.")
    parser.add_argument("--base-url", help="Ollama base URL. Defaults to local Ollama.")
    parser.add_argument(
        "--models-path",
        type=Path,
        default=_default_models_path(),
        help="Path used for disk free-space checks.",
    )
    parser.add_argument(
        "--start-ollama",
        action="store_true",
        help="Start `ollama serve` before querying or pulling models.",
    )

    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--list", action="store_true", help="List installed local models.")
    actions.add_argument("--show", metavar="MODEL", help="Show local model details.")
    actions.add_argument("--pull", metavar="MODEL", help="Pull a model with disk constraints.")

    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=40.0,
        help="Minimum free space that must remain on the models drive.",
    )
    parser.add_argument(
        "--max-download-gb",
        type=float,
        default=80.0,
        help="Maximum reported pull layer size allowed.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0, help="Ollama timeout.")
    parser.add_argument(
        "--background",
        action="store_true",
        help="Run a pull in a detached background process and write output to a log file.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        help="Log path for --background pulls. Defaults to .tmp/ollama-pulls/<model>.log.",
    )
    parser.add_argument(
        "--foreground-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.background and not args.pull:
        raise SystemExit("--background is only supported with --pull.")
    if args.foreground_child and args.background:
        raise SystemExit("--background and --foreground-child cannot be combined.")

    if args.list:
        _print_model_list(
            list_local_ollama_models(
                args.base_url,
                timeout_seconds=args.timeout_seconds,
                start_ollama=args.start_ollama,
            )
        )
        return

    if args.show:
        details = show_ollama_model(
            args.show,
            args.base_url,
            timeout_seconds=args.timeout_seconds,
            start_ollama=args.start_ollama,
        )
        _print_model_details(details)
        return

    if args.background:
        job = _start_background_pull(args)
        print(f"started_background_pull: {args.pull}")
        print(f"pid: {job.pid}")
        print(f"log_path: {job.log_path}")
        return

    constraints = OllamaPullConstraints.from_gib(
        min_free_gib=args.min_free_gb,
        max_download_gib=args.max_download_gb,
        models_path=args.models_path,
    )
    result = pull_ollama_model(
        args.pull,
        args.base_url,
        constraints=constraints,
        progress_callback=_print_pull_progress,
        timeout_seconds=args.timeout_seconds,
        start_ollama=args.start_ollama,
    )
    _print_pull_result(result.model, result.max_reported_total_bytes)


def _print_model_list(models: tuple[LocalOllamaModel, ...]) -> None:
    for model in models:
        print(f"{model.model}\t{model.size_bytes / 1024**3:.2f} GiB")


def _print_model_details(details: dict[str, object]) -> None:
    for key in ("model_info", "details", "license", "parameters"):
        if key in details:
            print(f"{key}: {details[key]}")


def _print_pull_result(model: str, total_bytes: int | None) -> None:
    print(f"pulled: {model}")
    if total_bytes is not None:
        print(f"max_reported_total_gb: {total_bytes / 1024**3:.2f}")


def _print_pull_progress(event: OllamaPullProgress) -> None:
    prefix = datetime.now(UTC).isoformat(timespec="seconds")
    parts = [prefix, f"status={event.status}"]
    if event.digest:
        parts.append(f"digest={event.digest}")
    if event.completed_bytes is not None and event.total_bytes is not None:
        percent = (event.completed_bytes / event.total_bytes) * 100 if event.total_bytes else 0
        parts.append(f"completed_gb={event.completed_bytes / 1024**3:.2f}")
        parts.append(f"total_gb={event.total_bytes / 1024**3:.2f}")
        parts.append(f"percent={percent:.1f}")
    print(" ".join(parts), flush=True)


def _default_models_path() -> Path:
    return Path("D:/AI/Ollama/models")


def _start_background_pull(args: argparse.Namespace) -> BackgroundPullJob:
    log_path = args.log_path or _default_log_path(args.pull)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--pull",
        args.pull,
        "--models-path",
        str(args.models_path),
        "--min-free-gb",
        str(args.min_free_gb),
        "--max-download-gb",
        str(args.max_download_gb),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--foreground-child",
    ]
    if args.base_url:
        command.extend(("--base-url", args.base_url))
    if args.start_ollama:
        command.append("--start-ollama")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log_file = log_path.open("ab")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
        )
    finally:
        log_file.close()

    return BackgroundPullJob(pid=process.pid, log_path=log_path)


def _default_log_path(model: str) -> Path:
    safe_name = model.replace("/", "_").replace(":", "-")
    return Path(".tmp") / "ollama-pulls" / f"{safe_name}.log"


class BackgroundPullJob:
    def __init__(self, *, pid: int, log_path: Path) -> None:
        self.pid = pid
        self.log_path = log_path


if __name__ == "__main__":
    main()
