from __future__ import annotations

import argparse
from pathlib import Path

from ai_provider import (
    LocalOllamaModel,
    OllamaPullConstraints,
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
    args = parser.parse_args()

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

    constraints = OllamaPullConstraints.from_gib(
        min_free_gib=args.min_free_gb,
        max_download_gib=args.max_download_gb,
        models_path=args.models_path,
    )
    result = pull_ollama_model(
        args.pull,
        args.base_url,
        constraints=constraints,
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


def _default_models_path() -> Path:
    return Path("D:/AI/Ollama/models")


if __name__ == "__main__":
    main()
