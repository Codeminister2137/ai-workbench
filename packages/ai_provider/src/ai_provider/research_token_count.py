"""Fingerprint-guarded local counts for the inspected research-review templates."""

from __future__ import annotations

import hashlib
import importlib
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from ai_provider.contracts import AIRequest

TEMPLATE_SHA256 = {
    "qwen3:14b": "ae370d884f108d16e7cc8fd5259ebc5773a0afa6e078b11f4ed7e39a27e0dfc4",
    "gpt-oss:20b": "fa6710a93d78da62641e192361344be7a8c0a1c3737f139cf89f20ce1626b99c",
}
TOKENIZER_SHA256 = {
    "qwen3:14b": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    "gpt-oss:20b": "0614fe83cadab421296e664e1f48f4261fa8fef6e03e63bb75c20f38e37d07d3",
}

MODEL_BLOB = {
    "qwen3:14b": "sha256-a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e",
    "gpt-oss:20b": "sha256-e7b273f9636059a689e3ddcab3716e4f65abe0143ac978e46673ad0e52d09efb",
}
RUNTIME_VERSION = "0.32.5"
TOKENIZERS_VERSION = "0.23.2"


def count_review_input_tokens(
    request: AIRequest,
    model_details: dict[str, Any],
    tokenizer_file: Path,
    *,
    runtime_version: str | None,
) -> int:
    """Count complete supported framing; reject unverifiable inputs for byte fallback.

    Assets are explicit local files. No downloads, private runtime endpoints,
    prompt persistence, padding or truncation are used. The caller owns deadlines.
    GPT framing is date-dependent and remains conservative because runtime
    timezone/date agreement is not established by a version/model fingerprint.
    """
    if runtime_version != RUNTIME_VERSION:
        raise ValueError("Runtime version has not been verified for exact counting")
    model = request.model
    if model not in MODEL_BLOB:
        raise ValueError("Model has no verified tokenizer profile")
    if model == "gpt-oss:20b":
        raise ValueError("Runtime date agreement is unverified; using conservative counting")
    if model_details.get("renderer") or model_details.get("system"):
        raise ValueError("Runtime renderer or default system instructions are unsupported")
    template = model_details.get("template")
    if not isinstance(template, str):
        raise ValueError("Installed template is unavailable")
    modelfile = model_details.get("modelfile")
    if not isinstance(modelfile, str):
        raise ValueError("Installed model identity is unavailable")
    if any(
        line.strip().startswith(("MESSAGE ", "SYSTEM ", "ADAPTER "))
        for line in modelfile.splitlines()
    ):
        raise ValueError("Additional model instructions, history or adapters are unsupported")
    blobs = [
        line[5:].strip().strip('"') for line in modelfile.splitlines() if line.startswith("FROM ")
    ]
    if len(blobs) != 1 or Path(blobs[0].replace("\\", "/")).name != MODEL_BLOB[model]:
        raise ValueError("Installed model identity does not match verified tokenizer profile")
    value = asdict(request)
    value["messages"] = list(value["messages"])
    rendered = render_research_review_prompt(
        value, template_sha256=hashlib.sha256(template.encode("utf-8")).hexdigest()
    )
    try:
        with tokenizer_file.open("rb") as file:
            asset = file.read(40 * 1024 * 1024 + 1)
    except OSError as error:
        raise ValueError("Local tokenizer asset is unavailable") from error
    if hashlib.sha256(asset).hexdigest() != TOKENIZER_SHA256[model]:
        raise ValueError("Local tokenizer digest does not match verified profile")
    try:
        library = importlib.import_module("tokenizers")
    except ImportError as error:
        raise ValueError("Optional tokenizers dependency is unavailable") from error
    if library.__version__ != TOKENIZERS_VERSION:
        raise ValueError("Tokenizer library version has not been verified")
    tokenizer = library.Tokenizer.from_str(asset.decode("utf-8"))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return len(tokenizer.encode(rendered, add_special_tokens=False).ids)


def render_research_review_prompt(
    request: dict[str, Any], *, template_sha256: str, current_date: str | None = None
) -> str:
    """Render only the inspected templates' two plain research-review messages.

    This diagnostic deliberately rejects other templates/models, tools, history
    and multimodal payloads instead of approximating their framing. The GPT-OSS
    template uses the runtime's date; callers must supply that exact date.
    """
    model = request.get("model")
    if (
        not isinstance(model, str)
        or model not in TEMPLATE_SHA256
        or template_sha256 != TEMPLATE_SHA256[model]
    ):
        raise ValueError("Unsupported model or installed template fingerprint")
    messages = request.get("messages")
    if request.get("tools") or not isinstance(messages, list) or len(messages) != 2:
        raise ValueError("Counting supports exactly two plain review messages without tools")
    for message, role in zip(messages, ("system", "user"), strict=True):
        if (
            not isinstance(message, dict)
            or message.get("role") != role
            or not isinstance(message.get("content"), str)
            or not message["content"]
            or message.get("tool_calls")
            or message.get("tool_call_id")
            or message.get("name")
            or set(message) - {"role", "content", "tool_calls", "tool_call_id", "name"}
        ):
            raise ValueError(
                "Counting requires one plain system message and one plain user message"
            )
    metadata = request.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Request metadata must be an object")
    thinking = metadata.get("ollama_thinking")
    system, user = (message["content"] for message in messages)
    if model == "qwen3:14b":
        if type(thinking) is not bool:
            raise ValueError(
                "Qwen counting requires explicit boolean thinking; native default is unverified"
            )
        suffix = " /think" if thinking else " /no_think"
        rendered = (
            "<|im_start|>system\n\n" + system + "<|im_end|>\n"
            "<|im_start|>user\n" + user + suffix + "<|im_end|>\n<|im_start|>assistant\n"
        )
        if thinking is False:
            rendered += "<think>\n\n</think>\n\n"
        return rendered
    if thinking not in (None, "high"):
        raise ValueError("GPT-OSS counting supports only native default or high effort")
    if current_date is None or date.fromisoformat(current_date).isoformat() != current_date:
        raise ValueError("GPT-OSS requires the exact runtime date in YYYY-MM-DD format")
    return (
        "<|start|>system<|message|>You are ChatGPT, a large language model trained by OpenAI.\n"
        "Knowledge cutoff: 2024-06\nCurrent date: "
        + current_date
        + "\n\nReasoning: "
        + (thinking or "medium")
        + "\n\n# Valid channels: analysis, commentary, final. "
        "Channel must be included for every message.<|end|>"
        "<|start|>developer<|message|>\n\n# Instructions\n\n" + system + "<|end|>"
        "<|start|>user<|message|>" + user + "<|end|><|start|>assistant"
    )
