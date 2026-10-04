"""Validated immutable settings persisted by the foreground research scheduler."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ai_orchestrator.review import ReviewSettings


@dataclass(frozen=True)
class ResearchTaskSettings:
    review_policy: str = "legacy"
    review_model: str | None = None
    review_mode: str = "auto"
    review_output_tokens: int = 4096
    review_timeout_seconds: float = 300.0
    review_tokenizer_file: str | None = None
    max_repair_cycles: int = 3

    def __post_init__(self) -> None:
        if self.review_policy not in ("legacy", "quality_first"):
            raise ValueError("Unsupported research review policy")
        if self.review_mode not in ("auto", "default", "direct", "deliberative"):
            raise ValueError("Unsupported research review mode")
        for value in (self.review_model, self.review_tokenizer_file):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("Reviewer model and tokenizer path must be nonempty strings")
        if not isinstance(self.review_timeout_seconds, (int, float)):
            raise ValueError("Research review timeout must be numeric")
        ReviewSettings(self.review_output_tokens, self.review_timeout_seconds)
        if (
            isinstance(self.max_repair_cycles, bool)
            or not isinstance(self.max_repair_cycles, int)
            or self.max_repair_cycles < -1
        ):
            raise ValueError("Max repair cycles must be -1 (budget bounded) or nonnegative")
        customized = (
            self.review_model is not None
            or self.review_mode != "auto"
            or self.review_output_tokens != 4096
            or self.review_timeout_seconds != 300
            or self.review_tokenizer_file is not None
        )
        if customized and self.review_policy != "quality_first":
            raise ValueError("Research review overrides require quality_first policy")

    def worker_arguments(self) -> list[str]:
        arguments = [
            "--research-review-policy",
            self.review_policy,
            "--research-review-mode",
            self.review_mode,
            "--research-review-output-tokens",
            str(self.review_output_tokens),
            "--research-review-timeout-seconds",
            str(self.review_timeout_seconds),
            "--max-repair-cycles",
            str(self.max_repair_cycles),
        ]
        for flag, value in (
            ("--research-review-model", self.review_model),
            ("--research-review-tokenizer-file", self.review_tokenizer_file),
        ):
            if value is not None:
                arguments.extend([flag, value])
        return arguments

    def to_json(self) -> str:
        return json.dumps(asdict(self), allow_nan=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> ResearchTaskSettings:
        try:
            values = json.loads(text)
            if not isinstance(values, dict):
                raise ValueError("Scheduled research settings must be a JSON object")
            return cls(**values)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid scheduled research settings") from error
