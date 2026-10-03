"""Plan or explicitly execute the approved local 24-case research review matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ai_agent.research_reports import validate_report
from ai_orchestrator import CostPolicyTier, TaskProfile, load_model_catalog
from ai_orchestrator.review import ReviewMode, ReviewSettings, ReviewWorkload, select_review_plan
from ai_orchestrator.scheduling import ScheduledTask, admit_task
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamEvent,
    BackendInfo,
    ChatClient,
    MessageRole,
)
from ai_provider.factory import create_chat_client
from ai_provider.research_review import ResearchReviewClient, review_input_token_upper_bound
from ai_provider.scrutiny import (
    RESEARCH_SCRUTINY_SYSTEM_PROMPT,
    build_research_scrutiny_prompt,
    parse_response_scrutiny_report,
)

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SECONDS = 90 * 60
VARIANTS = (
    ("qwen3_deliberative", "qwen3:14b", ReviewMode.DELIBERATIVE),
    ("qwen3_direct", "qwen3:14b", ReviewMode.DIRECT),
    ("gptoss_baseline", "gpt-oss:20b", ReviewMode.DEFAULT),
)


def load_corpus(path: Path) -> dict[str, Any]:
    """Validate evaluation-only fixtures and prevent whole-family holdout leakage."""
    corpus = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(corpus, dict):
        raise ValueError("Corpus must be a JSON object")
    if corpus.get("evaluation_only") is not True or corpus.get("public_only") is not True:
        raise ValueError("Corpus must explicitly declare evaluation-only public sources")
    cases = corpus.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("Representative matrix requires exactly 24 cases")
    families: dict[str, set[str]] = {}
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each case must be a JSON object")
        if (
            case.get("public_only") is not True
            or not isinstance(case.get("report"), str)
            or not case["report"].strip()
        ):
            raise ValueError("Each case requires a public-only report")
        case_id, family, split = case.get("id"), case.get("family"), case.get("split")
        if not isinstance(case_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", case_id
        ):
            raise ValueError("Case IDs must use 1–64 letters, digits, underscores or hyphens")
        if case_id.casefold() in ids:
            raise ValueError("Case IDs must be unique, including on case-insensitive filesystems")
        if (
            not isinstance(family, str)
            or not family.strip()
            or not isinstance(split, str)
            or split not in {"development", "holdout"}
        ):
            raise ValueError("Each case requires family and development/holdout split")
        ids.add(case_id.casefold())
        families.setdefault(family, set()).add(split)
        if not isinstance(case.get("original_prompt"), str) or not case["original_prompt"].strip():
            raise ValueError("Each case requires a nonempty original prompt")
        if not isinstance(case.get("expected"), dict) or not case["expected"]:
            raise ValueError("Each case requires expected audit findings outside reviewer input")
        if not isinstance(case.get("complexity", "unknown"), str):
            raise ValueError("Case complexity must be unknown, simple, or complex")
        ReviewWorkload(complexity=case.get("complexity", "unknown"))
        sources = case.get("sources")
        if not isinstance(sources, list) or len(sources) < 2:
            raise ValueError("Each case needs at least two public-source records")
        source_ids: set[str] = set()
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("Source records must be JSON objects")
            source_id = source.get("id")
            if not isinstance(source_id, str) or not re.fullmatch(r"S[1-9][0-9]*", source_id):
                raise ValueError("Source IDs must use S followed by a positive integer")
            if source_id in source_ids:
                raise ValueError("Source IDs must be unique within each case")
            source_ids.add(source_id)
            if not isinstance(source.get("url"), str):
                raise ValueError("Sources require HTTP(S) URL strings")
            parsed = urlsplit(source["url"])
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Sources require public HTTP(S) URLs without credentials")
            if not isinstance(source.get("receipt"), dict) or not source["receipt"]:
                raise ValueError("Each source requires a retrieval receipt object")
            if not isinstance(source.get("coverage"), str) or not source["coverage"].strip():
                raise ValueError("Each source requires an explicit coverage description")
            if not isinstance(source.get("excerpt_truncated"), bool):
                raise ValueError("Source excerpt_truncated must be a boolean")
            if source.get("synthetic_appendix") is not None and not isinstance(
                source["synthetic_appendix"], str
            ):
                raise ValueError("Untrusted synthetic appendices must be text")
            if not isinstance(source.get("segments"), list):
                raise ValueError(
                    "Source segments must be a list; missing coverage uses an empty list"
                )
            for segment in source["segments"]:
                if (
                    not isinstance(segment, dict)
                    or not isinstance(segment.get("text"), str)
                    or not segment["text"].strip()
                    or not isinstance(segment.get("sha256"), str)
                ):
                    raise ValueError("Selected source segments require nonempty text and a digest")
                if hashlib.sha256(segment["text"].encode()).hexdigest() != segment["sha256"]:
                    raise ValueError("Source excerpt digest does not match")
    if len(families) < 6 or any(len(splits) != 1 for splits in families.values()):
        raise ValueError("At least six families are required, held out by whole family")
    holdout = [case for case in cases if case["split"] == "holdout"]
    declared_holdout = corpus.get("holdout_families")
    if not isinstance(declared_holdout, list) or not all(
        isinstance(family, str) and family.strip() for family in declared_holdout
    ):
        raise ValueError("Holdout families must be a list of nonempty names")
    if len(declared_holdout) != len(set(declared_holdout)):
        raise ValueError("Holdout family names must be unique")
    if len(holdout) != 8 or set(declared_holdout) != {case["family"] for case in holdout}:
        raise ValueError("Exactly eight cases must be reserved in the declared holdout families")
    settings = corpus.get("settings_frozen")
    if not isinstance(settings, dict):
        raise ValueError("Corpus requires frozen review settings")
    ReviewSettings(settings["max_output_tokens"], settings["timeout_seconds"])
    if (
        type(settings["context_tokens"]) is not int
        or settings["context_tokens"] != 32768
        or settings["temperature"] != 0.2
    ):
        raise ValueError("Matched baseline requires 32768 context and temperature 0.2")
    return corpus


def request_for_case(case: dict[str, Any], model: str) -> AIRequest:
    """Render visible evidence without leaking expected findings into the request."""
    evidence = []
    for source in case["sources"]:
        evidence.append(
            f"Source {source['id']} URL: {source['url']}\n"
            "Actual retrieval receipt (execution, not entailment): "
            f"{json.dumps(source['receipt'])}\n"
            f"Coverage: {source['coverage']}; excerpt truncated: {source['excerpt_truncated']}\n"
        )
        for segment in source["segments"]:
            evidence.append(f"Selected untrusted source passage:\n{segment['text']}\n")
        if source.get("synthetic_appendix"):
            evidence.append(f"Untrusted source appendix:\n{source['synthetic_appendix']}\n")
    evidence.append("Candidate report (claims, not evidence):\n" + case["report"])
    errors = validate_report(case["report"], fetch_receipts=[s["receipt"] for s in case["sources"]])
    prompt = build_research_scrutiny_prompt(
        case["original_prompt"],
        "Evaluation fixture; no completed application run is claimed.",
        execution_status="evaluation_fixture",
        validation_evidence="Fixture structure/declared-source checks: "
        + (str(errors) if errors else "passed; no write/run receipt is claimed"),
        research_evidence="\n".join(evidence),
    )
    return AIRequest(
        (
            AIMessage(MessageRole.SYSTEM, RESEARCH_SCRUTINY_SYSTEM_PROMPT),
            AIMessage(MessageRole.USER, prompt),
        ),
        model=model,
        temperature=0.2,
    )


def matrix_plan(corpus: dict[str, Any], corpus_bytes: bytes) -> dict[str, Any]:
    settings = corpus["settings_frozen"]
    headrooms = [
        settings["context_tokens"]
        - review_input_token_upper_bound(request_for_case(case, "qwen3:14b"))
        - 256
        for case in corpus["cases"]
    ]
    return {
        "status": "PLANNED",
        "task_id": "representative-review-evaluation",
        "required_seconds": REQUIRED_SECONDS,
        "case_count": 24,
        "call_count": 72,
        "split_counts": dict(Counter(case["split"] for case in corpus["cases"])),
        "holdout_families": corpus["holdout_families"],
        "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        "settings_frozen": settings,
        "variants": [{"id": v, "model": m, "mode": mode.value} for v, m, mode in VARIANTS],
        "generation_headroom_min": min(headrooms),
        "context_rejected_case_ids": [
            case["id"] for case, room in zip(corpus["cases"], headrooms, strict=True) if room < 2048
        ],
        "notes": (
            "Planning does not invoke models. Completion of calls is distinct from "
            "a visible-answer quality audit and D4 activation. 72 initial calls; "
            "bounded truncation retries, if any, are recorded separately."
        ),
    }


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    temporary.replace(path)


@dataclass
class RecordingClient:
    """Save prepared public-fixture requests and raw responses before interpretation."""

    client: ChatClient
    record: dict[str, Any]
    persist: Callable[[], None]

    @property
    def backend(self) -> BackendInfo:
        return self.client.backend

    def complete(self, request: AIRequest) -> AIResponse:
        self.record.setdefault("prepared_requests", []).append(asdict(request))
        self.persist()
        response = self.client.complete(request)
        self.record.setdefault("raw_responses", []).append(asdict(response))
        self.persist()
        return response

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        raise ValueError("Evaluation records complete responses only")
        yield


def execute_matrix(
    corpus: dict[str, Any], plan: dict[str, Any], output: Path, deadline: float
) -> int:
    settings = corpus["settings_frozen"]
    review_settings = ReviewSettings(settings["max_output_tokens"], settings["timeout_seconds"])
    catalog = load_model_catalog(ROOT / "packages/ai_orchestrator/examples/model_catalog.toml")
    cases = sorted(corpus["cases"], key=lambda case: (case["split"] == "holdout", case["id"]))
    completed = []
    summary: dict[str, Any] = {
        **plan,
        "status": "RUNNING",
        "results": completed,
        "quality_audit_status": "PENDING",
    }
    save_json(output / "summary.json", summary)
    for index, case in enumerate(cases):
        started = time.perf_counter()
        selected = select_review_plan(
            TaskProfile(cost_policy_tier=CostPolicyTier.LOCAL_ONLY),
            catalog,
            ReviewWorkload(complexity=case.get("complexity", "unknown")),
            primary_model="gpt-oss:20b",
        )
        selector = {
            "model": selected.candidate.backend.model,
            "mode": selected.mode.value,
            "reasons": selected.reasons,
            "elapsed_seconds": time.perf_counter() - started,
        }
        order = VARIANTS[index % 3 :] + VARIANTS[: index % 3]
        for variant, model, mode in order:
            admission = admit_task(
                ScheduledTask(f"{case['id']}-{variant}", review_settings.timeout_seconds),
                explicitly_started=True,
                window_deadline=deadline,
                now=time.perf_counter(),
                constraints_satisfied=True,
            )
            if not admission.admitted:
                summary.update(status="INCOMPLETE", stop_reason=admission.reason)
                save_json(output / "summary.json", summary)
                return 1
            path = output / case["split"] / f"{case['id']}-{variant}.json"
            record: dict[str, Any] = {
                "case_id": case["id"],
                "family": case["family"],
                "split": case["split"],
                "variant": variant,
                "selector": selector,
                "expected": case["expected"],
                "started_at_utc": datetime.now(UTC).isoformat(),
                "audit": {},
                "status": "RUNNING",
            }
            request = request_for_case(case, model)

            def persist(record=record, path=path):
                save_json(path, record)

            def factory(config, record=record, persist=persist):
                return RecordingClient(create_chat_client(config), record, persist)

            client = ResearchReviewClient(
                BackendConfig(
                    ProviderKind.OLLAMA,
                    model,
                    base_url="http://localhost:11434",
                    timeout_seconds=review_settings.timeout_seconds,
                ),
                mode,
                settings["context_tokens"],
                review_settings,
                admission.deadline,
                details=record["audit"],
                client_factory=factory,
            )
            persist()
            call_started = time.perf_counter()
            print(f"review_matrix: {case['id']} {variant} started", flush=True)
            try:
                response = client.complete(request)
                report = parse_response_scrutiny_report(response.message.content)
                record.update(status="COMPLETED", format_valid=True, verdict=report.verdict)
            except Exception as error:
                record.update(
                    status="FAILED", format_valid=False, error=f"{type(error).__name__}: {error}"
                )
            record["elapsed_seconds"] = time.perf_counter() - call_started
            persist()
            completed.append(
                {
                    key: record[key]
                    for key in ("case_id", "variant", "status", "format_valid", "elapsed_seconds")
                }
            )
            save_json(output / "summary.json", summary)
            print(f"review_matrix: finished status={record['status']}", flush=True)
    summary.update(
        status="CALLS_COMPLETE", failed_call_count=sum(r["status"] == "FAILED" for r in completed)
    )
    save_json(output / "summary.json", summary)
    return 1 if summary["failed_call_count"] else 0


def main(argv: Sequence[str] | None = None) -> int:
    window_started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument(
        "--execute", action="store_true", help="Explicitly start this selected evaluation task"
    )
    parser.add_argument("--available-minutes", type=float)
    parser.add_argument("--handoff-reserve-minutes", type=float, default=10.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "artifacts"
        / ("research-review-evaluation-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")),
    )
    args = parser.parse_args(argv)
    try:
        # No automatic resume/reuse: a fresh directory protects previous evidence.
        output = args.output.resolve()
        if not output.is_relative_to((ROOT / "artifacts").resolve()) or output.exists():
            raise ValueError("Output must be a new directory inside repository artifacts")
        corpus_bytes = args.corpus.read_bytes()
        corpus = load_corpus(args.corpus)
        plan = matrix_plan(corpus, corpus_bytes)
        if not args.execute:
            print(json.dumps(plan, indent=2))
            return 0
        if (
            args.available_minutes is None
            or not math.isfinite(args.available_minutes)
            or args.available_minutes <= 0
        ):
            raise ValueError("Explicit execution requires positive finite --available-minutes")
        if not math.isfinite(args.handoff_reserve_minutes) or args.handoff_reserve_minutes < 0:
            raise ValueError("Handoff reserve must be finite and nonnegative")
        now = time.perf_counter()
        admission = admit_task(
            ScheduledTask(plan["task_id"], REQUIRED_SECONDS),
            explicitly_started=True,
            window_deadline=window_started
            + (args.available_minutes - args.handoff_reserve_minutes) * 60,
            now=now,
            constraints_satisfied=True,
        )
        if not admission.admitted:
            print(json.dumps({**plan, "admission": asdict(admission)}, indent=2))
            return 1
        if plan["context_rejected_case_ids"]:
            raise ValueError("Corpus contains cases that fail full-evidence context admission")
        assert admission.deadline is not None
        return execute_matrix(corpus, plan, output, admission.deadline)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
