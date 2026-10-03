"""Offline tokenizer probe for a supplied rendered prompt; never changes admission.

Requires separately approved installation of Hugging Face tokenizers and a local
tokenizer.json. No downloads, inference, model weights or runtime probes occur.
Counts describe these exact files, not an unverified Ollama chat serialization.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

from ai_provider.research_token_count import TEMPLATE_SHA256 as TEMPLATE_SHA256
from ai_provider.research_token_count import (
    TOKENIZER_SHA256,
    render_research_review_prompt,
)


def _count_text(tokenizer_bytes: bytes, prompt_bytes: bytes) -> dict[str, Any]:
    prompt = prompt_bytes.decode("utf-8")
    library = importlib.import_module("tokenizers")
    tokenizer = library.Tokenizer.from_str(tokenizer_bytes.decode("utf-8"))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    encoding = tokenizer.encode(prompt, add_special_tokens=False)
    return {
        "status": "PROTOTYPE_ONLY",
        "token_count": len(encoding.ids),
        "utf8_bytes": len(prompt_bytes),
        "tokenizer_sha256": hashlib.sha256(tokenizer_bytes).hexdigest(),
        "rendered_prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "tokenizers_version": library.__version__,
        "runtime_compatibility": "UNVERIFIED",
        "production_admission_changed": False,
    }


def count_rendered_prompt(tokenizer_file: Path, prompt_file: Path) -> dict[str, Any]:
    tokenizer_bytes = tokenizer_file.read_bytes()
    prompt_bytes = prompt_file.read_bytes()
    # A supplied tokenizer may contain production truncation/padding settings.
    # Neither may affect a diagnostic count of the complete rendered prompt.
    return _count_text(tokenizer_bytes, prompt_bytes)


def count_review_request(
    tokenizer_file: Path,
    request_file: Path,
    template_file: Path,
    *,
    current_date: str | None = None,
) -> dict[str, Any]:
    request = json.loads(request_file.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise ValueError("Request must be a JSON object")
    template = template_file.read_bytes()
    fingerprint = hashlib.sha256(template).hexdigest()
    rendered = render_research_review_prompt(
        request, template_sha256=fingerprint, current_date=current_date
    )
    tokenizer = tokenizer_file.read_bytes()
    if hashlib.sha256(tokenizer).hexdigest() != TOKENIZER_SHA256[request["model"]]:
        raise ValueError("Tokenizer asset does not match the inspected model fingerprint")
    result = _count_text(tokenizer, rendered.encode())
    result.update(
        model=request["model"],
        template_sha256=fingerprint,
        scope="Inspected two-message template; compare against runtime before admission",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer-file", type=Path, required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--rendered-prompt-file", type=Path)
    inputs.add_argument("--request-file", type=Path)
    parser.add_argument("--template-file", type=Path)
    parser.add_argument("--runtime-date")
    args = parser.parse_args(argv)
    try:
        if args.request_file:
            if args.template_file is None:
                parser.error("--request-file requires --template-file")
            result = count_review_request(
                args.tokenizer_file,
                args.request_file,
                args.template_file,
                current_date=args.runtime_date,
            )
        else:
            result = count_rendered_prompt(args.tokenizer_file, args.rendered_prompt_file)
    except ModuleNotFoundError:
        parser.error("Optional tokenizers dependency is absent; approve installation separately")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
