"""PASS-gated micro-evaluation ladder across reachable chat routes (L3 evidence).

T0 completes a three-line function; T1 implements a small two-function
module; T2 repairs a buggy function; T3 builds a module from a short spec.
Each route attempts T(n+1) only after Tn passes, so a failing route spends
nothing further. Prompts are synthetic and carry no repository content
(PUBLIC_OR_LOW_RISK with the ADR-063 public attestation), grading is
deterministic bare-namespace exec (temperature 0.0, one attempt per task, no
retries), and usage plus a planning-only cost estimate are recorded when the
provider reports usage.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from ai_provider import route_probe
from ai_provider.adapters.baseten import BASETEN_HACKATHON_MODEL
from ai_provider.adapters.openai_compatible import _zero_price_row
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.factory import create_chat_client
from ai_provider.secrets import load_dotenv
from ai_provider.source_info import _utc_now

TASK = (
    "Complete this Python function so add2(2) returns 4. "
    "Reply with ONLY the completed function in a ```python block, no explanation:\n"
    "```python\ndef add2(x):\n    return\n```"
)
MAX_OUTPUT_TOKENS = 1024

TASK_T1 = (
    "Implement two pure functions so the examples hold. "
    "Reply with ONLY the functions in a ```python block, no explanation. "
    "Use only plain arithmetic, comparisons, if/else, and for/while loops: "
    "no builtin functions (no len/range/sum), no imports, no printing:\n"
    "```python\n"
    "def clamp(value, lo, hi):\n"
    "    return\n"
    "\n"
    "def retry_delay_ms(base_ms, factor, attempt):\n"
    "    return\n"
    "```\n"
    "clamp returns value limited to [lo, hi]. retry_delay_ms returns "
    "base_ms * factor**attempt with attempt counting from 0. Examples: "
    "clamp(5, 0, 10) == 5; clamp(-3, 0, 10) == 0; "
    "retry_delay_ms(100, 2, 0) == 100; retry_delay_ms(100, 2, 3) == 800."
)
MAX_OUTPUT_TOKENS_T1 = 2048

TASK_T2 = (
    "This function has a bug: is_retryable(500) should be True but it returns "
    "False. Reply with ONLY the fixed function in a ```python block, no "
    "explanation. Use only plain comparisons and if/else: no builtin "
    "functions, no imports:\n"
    "```python\n"
    "def is_retryable(status):\n"
    "    return status == 429\n"
    "```\n"
    "It must return True for status 429 and for any 5xx status (500-599 "
    "inclusive), and False otherwise. Failing test: is_retryable(500) == True."
)
MAX_OUTPUT_TOKENS_T2 = 2048

TASK_T3 = (
    "Implement a small statistics module with these three functions. Reply "
    "with ONLY the functions in a ```python block, no explanation. Use only "
    "plain arithmetic, comparisons, if/else, and for/while loops over the "
    "input lists: no builtin functions (no len/sum/min/max), no printing. "
    "You may `import math`; any other import fails.\n"
    "- mean(values): arithmetic mean of a non-empty list of numbers.\n"
    "- stragglers(values, band): the values strictly outside "
    "[mean(values) - band, mean(values) + band], in input order. band >= 0.\n"
    "- rmse(values, target): square root of the mean squared deviation from "
    "target (math.sqrt is allowed).\n"
    "For example, mean([2, 4]) is 3.0, and stragglers([0, 10], 1) returns both "
    "inputs in order. (Illustrative only; grading uses other values.)"
)
MAX_OUTPUT_TOKENS_T3 = 4096

TASKS: tuple[str, ...] = ("T0", "T1", "T2", "T3")

CANDIDATE_TIMEOUT_SECONDS = 2.0
"""Wall-clock bound for grading one candidate answer (exec + assertions)."""


@dataclasses.dataclass(frozen=True)
class EvalResult:
    """Deterministic outcome of one route's evaluation on one ladder task."""

    route: str
    model: str
    checked_utc: str
    passed: bool
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    task_id: str = "T0"
    cost_usd_est: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def summary(self) -> str:
        where = f"{self.route}/{self.task_id} ({self.model})"
        if self.error:
            return f"{where}: ERROR {self.error}"
        verdict = "PASS" if self.passed else "FAIL"
        usage = (
            f"{self.input_tokens}/{self.output_tokens}t"
            if self.input_tokens is not None
            else "usage-unknown"
        )
        cost = f" ~${self.cost_usd_est:.4f}" if self.cost_usd_est is not None else ""
        return f"{where}: {verdict} {self.latency_ms}ms {usage}{cost}"


def check_completion(text: str) -> bool:
    """Run the returned function in a bare namespace and assert add2(2) == 4."""
    block = text
    if "```" in text:
        parts = text.split("```")
        candidates = [part for part in parts if "def add2" in part]
        if not candidates:
            return False
        block = candidates[0]
        if block.lstrip().startswith("python"):
            block = block.lstrip()[len("python") :]
    namespace: dict[str, Any] = {"__builtins__": {}}
    try:
        # Bare namespace without builtins: the snippet can only define add2.
        exec(compile(block, "<eval>", "exec"), namespace)
    except Exception:
        return False
    candidate = namespace.get("add2")
    if not callable(candidate):
        return False
    try:
        return bool(candidate(2) == 4)
    except Exception:
        return False


_SAFE_MODULES: dict[str, Any] = {"math": math, "re": re, "json": json}
"""Named-safe modules a task spec may allow; everything else stays banned."""


def _extract_block(text: str, symbols: tuple[str, ...]) -> str | None:
    """First fenced block defining a wanted symbol, or the raw text unfenced."""
    block = text
    if "```" in text:
        parts = text.split("```")
        candidates = [part for part in parts if any(marker in part for marker in symbols)]
        if not candidates:
            return None
        block = candidates[0]
        stripped = block.lstrip()
        if stripped.startswith("python"):
            block = stripped[len("python") :]
    return block


def _candidate_namespace(safe_modules: tuple[str, ...]) -> dict[str, Any]:
    """Bare namespace: no builtins, only the task's named-safe modules.

    Allowed modules are pre-bound AND importable through a restricted
    ``__import__``, so both bare ``math.sqrt`` and ``import math`` styles
    work. Any other import raises ImportError; any builtin raises NameError.
    """
    allowed = frozenset(safe_modules)

    def _restricted_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in allowed:
            return _SAFE_MODULES[name]
        raise ImportError(f"import of {name!r} is not allowed in eval answers")

    namespace: dict[str, Any] = {"__builtins__": {"__import__": _restricted_import}}
    for name in allowed:
        namespace[name] = _SAFE_MODULES[name]
    return namespace


def _exec_candidate(block: str, safe_modules: tuple[str, ...]) -> dict[str, Any] | None:
    """Exec one answer in a bare namespace; None when it fails to define."""
    try:
        namespace = _candidate_namespace(safe_modules)
        exec(compile(block, "<eval>", "exec"), namespace)
    except Exception:
        return None
    return namespace


def _run_guarded(
    block: str,
    check: Callable[[dict[str, Any]], bool],
    safe_modules: tuple[str, ...],
    timeout_seconds: float = CANDIDATE_TIMEOUT_SECONDS,
) -> bool:
    """Exec plus assertions with a wall-clock bound (2 s per the design).

    A candidate that never returns keeps its daemon worker until process
    exit; the grade itself always resolves at the timeout.
    """
    outcome: list[bool] = []

    def attempt() -> None:
        try:
            namespace = _exec_candidate(block, safe_modules)
            outcome.append(namespace is not None and check(namespace))
        except Exception:
            outcome.append(False)

    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    return len(outcome) == 1 and outcome[0]


def _grade(
    text: str,
    *,
    symbols: tuple[str, ...],
    check: Callable[[dict[str, Any]], bool],
    safe_modules: tuple[str, ...] = (),
    timeout_seconds: float = CANDIDATE_TIMEOUT_SECONDS,
) -> bool:
    """Grade one answer: extract the code block, exec bare, run assertions."""
    block = _extract_block(text, symbols)
    if block is None:
        return False
    return _run_guarded(block, check, safe_modules, timeout_seconds)


_T1_CLAMP_CASES = (
    # First two rows are the prompt's visible examples; the rest are held.
    (5, 0, 10, 5),
    (-3, 0, 10, 0),
    (99, 0, 10, 10),
    (0, 0, 10, 0),
    (10, 0, 10, 10),
    (7, 7, 7, 7),
    (2.5, 0, 1, 1),
    (-5, -10, -1, -5),
)
_T1_DELAY_CASES = (
    (100, 2, 0, 100),
    (100, 2, 3, 800),
    (50, 1, 5, 50),
    (10, 3, 2, 90),
    (100, 0.5, 2, 25.0),
    (200, 2, 10, 204800),
)


def check_t1(text: str) -> bool:
    """Grade the T1 small module: clamp plus retry_delay_ms over held edges."""

    def check(namespace: dict[str, Any]) -> bool:
        clamp = namespace.get("clamp")
        delay = namespace.get("retry_delay_ms")
        if not callable(clamp) or not callable(delay):
            return False
        try:
            for value, lo, hi, want in _T1_CLAMP_CASES:
                if clamp(value, lo, hi) != want:
                    return False
            for base, factor, attempt, want in _T1_DELAY_CASES:
                if delay(base, factor, attempt) != want:
                    return False
        except Exception:
            return False
        return True

    return _grade(text, symbols=("def clamp", "def retry_delay_ms"), check=check)


_T2_CASES = (
    # (status, retryable): the 500 row is the prompt's failing test.
    (429, True),
    (500, True),
    (502, True),
    (503, True),
    (504, True),
    (598, True),
    (599, True),
    (200, False),
    (400, False),
    (404, False),
    (499, False),
    (600, False),
)


def check_t2(text: str) -> bool:
    """Grade the T2 repair: the failing test plus the regression set."""

    def check(namespace: dict[str, Any]) -> bool:
        candidate = namespace.get("is_retryable")
        if not callable(candidate):
            return False
        try:
            for status, want in _T2_CASES:
                if candidate(status) is not want:
                    return False
        except Exception:
            return False
        return True

    return _grade(text, symbols=("def is_retryable",), check=check)


_T3_MEAN_CASES = (
    ((1, 2, 3), 2.0),
    ((5,), 5.0),
    ((0, 0, 0, 10), 2.5),
    ((-4, 4), 0.0),
    ((1.5, 2.5), 2.0),
    ((10, 20, 30, 40), 25.0),
)
_T3_STRAGGLER_CASES = (
    ((2, 4, 4, 4, 5, 9), 2, [2, 9]),
    ((1, 2, 3, 4, 100), 10, [1, 2, 3, 4, 100]),
    ((10, 10, 10), 0, []),
    ((50, 1, 2, 3), 5, [50, 1, 2, 3]),
    ((7,), 1, []),
)
_T3_RMSE_CASES = (
    ((4, 6), 5, 1.0),
    ((2, 8), 5, 3.0),
    ((5, 5), 5, 0.0),
    ((5, 5, 5, 9), 5, 2.0),
)


def check_t3(text: str) -> bool:
    """Grade the T3 spec build: mean, stragglers, rmse, all hidden tests."""

    def check(namespace: dict[str, Any]) -> bool:
        mean: Callable[..., Any] | None = namespace.get("mean")
        stragglers: Callable[..., Any] | None = namespace.get("stragglers")
        rmse: Callable[..., Any] | None = namespace.get("rmse")
        if not callable(mean) or not callable(stragglers) or not callable(rmse):
            return False
        try:
            for values, want in _T3_MEAN_CASES:
                if mean(list(values)) != want:
                    return False
            for values, band, want in _T3_STRAGGLER_CASES:
                if stragglers(list(values), band) != want:
                    return False
            for values, target, want in _T3_RMSE_CASES:
                if not math.isclose(rmse(list(values), target), want, rel_tol=1e-9):
                    return False
        except Exception:
            return False
        return True

    return _grade(
        text,
        symbols=("def mean", "def stragglers", "def rmse"),
        check=check,
        safe_modules=("math",),
    )


@dataclasses.dataclass(frozen=True)
class TaskSpec:
    """One ladder task: synthetic prompt, output cap, and grader."""

    task_id: str
    prompt: str
    max_output_tokens: int
    check: Callable[[str], bool]


TASK_SPECS: dict[str, TaskSpec] = {
    "T0": TaskSpec("T0", TASK, MAX_OUTPUT_TOKENS, check_completion),
    "T1": TaskSpec("T1", TASK_T1, MAX_OUTPUT_TOKENS_T1, check_t1),
    "T2": TaskSpec("T2", TASK_T2, MAX_OUTPUT_TOKENS_T2, check_t2),
    "T3": TaskSpec("T3", TASK_T3, MAX_OUTPUT_TOKENS_T3, check_t3),
}


def _short_error(error: Exception) -> str:
    """Exception type plus a credential-scrubbed message snippet."""
    scrubbed = re.sub(r"[A-Za-z0-9_-]{32,}", "***", str(error))
    return f"{type(error).__name__}: {scrubbed[:150]}"


_FREE_TIER_ROUTES = frozenset({"openrouter", "requesty"})
"""Routes whose model selection enforces free-tier picks (see select_model)."""

_SPARK_STANDARD_PER_MTOK = (1.25, 4.25)
"""Planning-only Meta rate: $1.25 input / $4.25 output per M tokens."""


def estimate_cost_usd(
    route: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """Planning-only cost estimate: price table times usage.

    Provider billing is truth. Free-tier routes estimate $0; routes without
    a planning rate return None rather than an imputed guess.
    """
    if input_tokens is None or output_tokens is None:
        return None
    if route in _FREE_TIER_ROUTES:
        return 0.0
    if route == "meta":
        per_input, per_output = _SPARK_STANDARD_PER_MTOK
        return (input_tokens * per_input + output_tokens * per_output) / 1_000_000
    return None


_PARKED_CATEGORIES = frozenset(
    {
        ProviderErrorCategory.AUTHENTICATION,
        ProviderErrorCategory.RATE_LIMIT,
        ProviderErrorCategory.USAGE_LIMIT,
    }
)
_PARKED_STATUS = re.compile(r"\b(401|403|429)\b")


def _is_parked_refusal(error: Exception) -> bool:
    """Account-level refusals (auth/rate-limit, incl. raw 401/403/429 markers).

    Observed shapes: Requesty-Novita HTTP 403 edge refusals, OpenCode HTTP
    429 account limits. A parked route stops the ladder with no retry-spend.
    """
    if isinstance(error, ProviderError) and error.category in _PARKED_CATEGORIES:
        return True
    return bool(_PARKED_STATUS.search(str(error)))


def run_eval(client: Any, route: str, model: str, *, task_id: str = "T0") -> EvalResult:
    """Send one ladder task through one client and grade deterministically."""
    spec = TASK_SPECS.get(task_id)
    if spec is None:
        raise ValueError(f"unknown route-eval task: {task_id!r}")
    checked = _utc_now()
    request = AIRequest(
        messages=(AIMessage(MessageRole.USER, spec.prompt),),
        temperature=0.0,
        max_output_tokens=spec.max_output_tokens,
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        # Fixed synthetic prompt: satisfies the ADR-063 public attestation
        # branch of the OpenRouter free-tier retention guard.
        metadata={"public_or_synthetic": True},
    )
    started = time.monotonic()
    try:
        response = client.complete(request)
    except Exception as error:
        short = _short_error(error)
        if _is_parked_refusal(error):
            short = f"parked:{short}"
        return EvalResult(route, model, checked, False, None, None, None, short, task_id=task_id)
    latency_ms = int((time.monotonic() - started) * 1000)
    usage = response.usage
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    return EvalResult(
        route,
        model,
        checked,
        spec.check(response.message.content or ""),
        latency_ms,
        input_tokens,
        output_tokens,
        None,
        task_id=task_id,
        cost_usd_est=estimate_cost_usd(route, input_tokens, output_tokens),
    )


def run_ladder(
    client: Any,
    route: str,
    model: str,
    *,
    tasks: tuple[str, ...] = TASKS,
    stop_on_fail: bool = True,
) -> list[EvalResult]:
    """Attempt ladder tasks in order; PASS-gated by default.

    With gating (the default), the first FAIL or transport error ends the
    ladder so a failing route spends nothing further. Pass
    ``stop_on_fail=False`` to collect a full card on $0 free-tier routes.
    Results stay in task order, so evidence consumers read the last row per
    route as the ladder verdict.
    """
    results = []
    for task_id in tasks:
        result = run_eval(client, route, model, task_id=task_id)
        results.append(result)
        if stop_on_fail and not result.passed:
            break
    return results


def capability_cards(results: list[EvalResult]) -> list[dict[str, Any]]:
    """Group per-task results into one capability card per (route, model).

    Each card carries pass/fail per task, latency, tokens, the planning
    cost estimate, and the error class on failure; ``parked`` marks routes
    stopped by an account-level refusal (ungraded, never imputed).
    """
    cards: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        key = (result.route, result.model)
        card = cards.get(key)
        if card is None:
            card = {
                "route": result.route,
                "model": result.model,
                "checked_utc": result.checked_utc,
                "tasks": {},
                "parked": False,
            }
            cards[key] = card
        card["checked_utc"] = max(card["checked_utc"], result.checked_utc)
        card["tasks"][result.task_id] = {
            "passed": result.passed,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd_est": result.cost_usd_est,
            "error": result.error,
        }
        if result.error is not None and result.error.startswith("parked:"):
            card["parked"] = True
    return list(cards.values())


def _list_rows(route: str, credentials: dict[str, str | None]) -> list[dict]:
    """Raw model rows from a route's live list endpoint (for model selection)."""
    import urllib.request

    entry = next(item for item in route_probe.ROUTES if item[0] == route)
    _, url, env_name = entry
    headers = {"User-Agent": route_probe.USER_AGENT, "Accept": "application/json"}
    if env_name and credentials.get(env_name):
        headers["Authorization"] = f"Bearer {credentials[env_name]}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers, method="GET"), timeout=15
        ) as response:
            raw = json.loads(response.read(route_probe._MAX_BYTES + 1).decode("utf-8"))
    except Exception:
        return []
    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        rows = raw.get("models") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _list_model_ids(route: str, credentials: dict[str, str | None]) -> list[str]:
    """All model ids from a route's live list endpoint (for model selection)."""
    rows = _list_rows(route, credentials)
    ids = [row.get("id") for row in rows]
    if not any(ids):
        ids = [row.get("name") for row in rows]
    return [str(item) for item in ids if item]


def select_model(route: str, credentials: dict[str, str | None]) -> str | None:
    """Cheapest defensible model id per route, or None to skip the route."""
    if route == "meta":
        return "muse-spark-1.3"
    if route == "baseten":
        return BASETEN_HACKATHON_MODEL
    if route == "requesty":
        # Same zero-price rule the completion guard enforces live.
        rows = _list_rows(route, credentials)
        free = [
            row["id"] for row in rows if isinstance(row.get("id"), str) and _zero_price_row(row)
        ]
        return free[0] if free else None
    ids = _list_model_ids(route, credentials)
    if route == "openrouter":
        free = [item for item in ids if item.endswith(":free")]
        return free[0] if free else None
    if route == "opencode_go":
        cheap = [
            item for item in ids if any(tag in item.lower() for tag in ("flash", "mini", "haiku"))
        ]
        return (cheap or ids or [None])[0]
    return None


_PROVIDERS: dict[str, tuple[ProviderKind, str, float, bool]] = {
    "meta": (ProviderKind.META, "META_API_KEY", 90.0, False),
    "baseten": (ProviderKind.BASETEN, "BASETEN_HACKATHON_API_KEY", 150.0, False),
    "openrouter": (ProviderKind.OPENROUTER, "OPENROUTER_API_KEY", 90.0, False),
    "requesty": (ProviderKind.REQUESTY, "REQUESTY_API_KEY", 90.0, True),
    "opencode_go": (ProviderKind.OPENCODE_GO, "OPENCODE_API_KEY", 90.0, False),
}


def _clients(credentials: dict[str, str | None]) -> dict[str, Callable[[str], Any]]:
    def make(route: str) -> Callable[[str], Any]:
        def build(model: str) -> Any:
            provider, env_name, timeout, free_only = _PROVIDERS[route]
            return create_chat_client(
                BackendConfig(
                    provider,
                    model,
                    None,
                    credentials.get(env_name) or None,
                    timeout,
                    require_free_model=free_only,
                )
            )

        return build

    return {route: make(route) for route in _PROVIDERS}


def run_all(
    credentials: dict[str, str | None], *, tasks: tuple[str, ...] = TASKS
) -> list[EvalResult]:
    """Run the ladder on every route with a selectable model; skips recorded."""
    gate = tasks[0] if tasks else "T0"
    factories = _clients(credentials)
    results = []
    for route, build in factories.items():
        try:
            model = select_model(route, credentials)
        except Exception as error:
            results.append(
                EvalResult(
                    route,
                    "?",
                    _utc_now(),
                    False,
                    None,
                    None,
                    None,
                    f"select:{type(error).__name__}",
                    task_id=gate,
                )
            )
            continue
        if model is None:
            results.append(
                EvalResult(
                    route, "?", _utc_now(), False, None, None, None, "no-model", task_id=gate
                )
            )
            continue
        results.extend(run_ladder(build(model), route, model, tasks=tasks))
    return results


def _snapshot_name(tasks: tuple[str, ...], stamp: str) -> str:
    """Snapshot filename carrying the attempted task ids (1 file per run)."""
    if tasks == TASKS:
        label = "T0-T3"
    elif len(tasks) == 1:
        label = tasks[0]
    elif tasks:
        label = "-".join(tasks)
    else:
        label = "empty"
    return f"route-eval-{label}-{stamp}.json"


def main(argv: list[str] | None = None) -> int:
    """Live CLI: run the ladder on reachable routes, write a dated snapshot."""
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=Path("artifacts/route-evals"))
    parser.add_argument("--routes", nargs="*", default=None)
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=None,
        help=f"task ids in ladder order (default: {' '.join(TASKS)})",
    )
    parser.add_argument(
        "--continue-past-fail",
        action="store_true",
        help="run every requested task even after a FAIL (default: PASS-gated)",
    )
    args = parser.parse_args(argv)
    tasks = tuple(args.tasks) if args.tasks is not None else TASKS
    unknown = [task for task in tasks if task not in TASK_SPECS]
    if unknown:
        parser.error(f"unknown task id(s): {', '.join(unknown)} (choose from {' '.join(TASKS)})")
    gate = tasks[0] if tasks else "T0"
    load_dotenv()
    credentials = {
        name: os.getenv(name) or None
        for name in (
            "META_API_KEY",
            "BASETEN_HACKATHON_API_KEY",
            "OPENROUTER_API_KEY",
            "REQUESTY_API_KEY",
            "OPENCODE_API_KEY",
        )
    }
    factories = _clients(credentials)
    wanted = args.routes or list(factories)
    results = []
    for route in wanted:
        model = select_model(route, credentials)
        if model is None:
            results.append(
                EvalResult(
                    route, "?", _utc_now(), False, None, None, None, "no-model", task_id=gate
                )
            )
            continue
        results.extend(
            run_ladder(
                factories[route](model),
                route,
                model,
                tasks=tasks,
                stop_on_fail=not args.continue_past_fail,
            )
        )
    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    snapshot = args.snapshot_dir / _snapshot_name(tasks, stamp)
    snapshot.write_text(
        json.dumps([item.to_dict() for item in results], indent=2), encoding="utf-8"
    )
    for item in results:
        print(item.summary())
    print(f"snapshot: {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
