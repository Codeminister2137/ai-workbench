from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
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
    actions.add_argument(
        "--pull-status",
        action="store_true",
        help="Show background pull status from logs and installed local models.",
    )

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

    if args.pull_status:
        _print_pull_status(
            log_dir=_default_log_dir(),
            installed_models=list_local_ollama_models(
                args.base_url,
                timeout_seconds=args.timeout_seconds,
                start_ollama=args.start_ollama,
            ),
        )
        return

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


def _print_pull_status(
    *,
    log_dir: Path,
    installed_models: tuple[LocalOllamaModel, ...],
) -> None:
    installed_by_model = {model.model: model for model in installed_models}
    log_paths = tuple(sorted(log_dir.glob("*.log"))) if log_dir.exists() else ()
    if not log_paths:
        print("background_pulls: none")
    else:
        for log_path in log_paths:
            status = _pull_status_from_log(log_path)
            installed = installed_by_model.get(status.model)
            installed_text = (
                f"installed_gb={installed.size_bytes / 1024**3:.2f}"
                if installed is not None
                else "installed=no"
            )
            progress_text = (
                f"progress={status.percent:.1f}%"
                if status.percent is not None
                else "progress=unknown"
            )
            total_text = (
                f"completed_gb={status.completed_bytes / 1024**3:.2f} "
                f"total_gb={status.total_bytes / 1024**3:.2f}"
                if status.completed_bytes is not None and status.total_bytes is not None
                else "completed_gb=unknown total_gb=unknown"
            )
            print(
                " ".join(
                    (
                        f"model={status.model}",
                        f"status={status.status}",
                        progress_text,
                        total_text,
                        installed_text,
                        f"log={log_path}",
                    )
                )
            )

    if installed_models:
        print("installed_models:")
        _print_model_list(installed_models)
    else:
        print("installed_models: none")


def _pull_status_from_log(log_path: Path) -> PullLogStatus:
    model = _model_from_log_path(log_path)
    last_line = ""
    with log_path.open("r", encoding="utf-8", errors="replace") as log_file:
        for line in log_file:
            if line.strip():
                last_line = line.strip()
    if not last_line:
        return PullLogStatus(model=model, status="pending")

    fields = _parse_progress_line(last_line)
    return PullLogStatus(
        model=model,
        status=fields.get("status", "unknown"),
        completed_bytes=_gib_to_bytes(fields.get("completed_gb")),
        total_bytes=_gib_to_bytes(fields.get("total_gb")),
        percent=_to_float(fields.get("percent")),
    )


def _parse_progress_line(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        key, separator, value = token.partition("=")
        if separator:
            fields[key] = value
    return fields


def _gib_to_bytes(value: str | None) -> int | None:
    number = _to_float(value)
    return int(number * 1024**3) if number is not None else None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _model_from_log_path(log_path: Path) -> str:
    name, separator, tag = log_path.stem.rpartition("-")
    return f"{name}:{tag}" if separator else log_path.stem


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
    return _default_log_dir() / f"{safe_name}.log"


def _default_log_dir() -> Path:
    return Path(".tmp") / "ollama-pulls"


@dataclass(frozen=True, slots=True)
class PullLogStatus:
    model: str
    status: str
    completed_bytes: int | None = None
    total_bytes: int | None = None
    percent: float | None = None


class BackgroundPullJob:
    def __init__(self, *, pid: int, log_path: Path) -> None:
        self.pid = pid
        self.log_path = log_path


if __name__ == "__main__":
    main()
