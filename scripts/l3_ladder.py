"""Orchestrator-driven L3 ladder: resolve candidates, tier-gate, walk, snapshot.

Policy lives here on the caller side (ADR-080); mechanism (walk, grade,
snapshot) lives in ``ai_provider.route_eval``. The provider layer never
imports the orchestrator: this script resolves an ordered, tier-gated
candidate list per route and hands it to the walk.

Cost-tier enforcement: every route has a ceiling tier and the run declares
an allowance (``--allow-tier``). A route whose ceiling exceeds the allowance
is recorded as ``tier-blocked`` and never attempted — cost tiers are never
escalated without an explicit flag. Free routes additionally never resolve
paid candidates, matching the provider guards.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/ai_provider/src"))
sys.path.insert(0, str(ROOT / "packages/ai_orchestrator/src"))

from ai_orchestrator import (  # noqa: E402
    CostPolicyTier,
    PrivacyClass,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
    cost_policy_allows,
    load_model_catalog,
    recommend_model,
)
from ai_provider import route_eval  # noqa: E402
from ai_provider.route_eval import TASK_SPECS, TASKS, EvalResult  # noqa: E402
from ai_provider.secrets import load_dotenv  # noqa: E402

EVAL_ROUTES = ("meta", "baseten", "openrouter", "requesty", "opencode_go")
"""Routes the ladder measures, in run order."""

ROUTE_TIERS = {
    "openrouter": CostPolicyTier.FREE_ONLY,
    "requesty": CostPolicyTier.FREE_ONLY,
    "opencode_go": CostPolicyTier.ALLOWANCES_ALLOWED,
    "baseten": CostPolicyTier.PREPAID_CREDITS_ALLOWED,
    "meta": CostPolicyTier.PREPAID_CREDITS_ALLOWED,
}
"""Ceiling tier per eval route; the meta ceiling matches its catalog entry."""

FREE_ROUTES = frozenset({"openrouter", "requesty"})
"""Routes whose candidates resolve live from $0-verified listings."""

CREDENTIAL_NAMES = (
    "META_API_KEY",
    "BASETEN_HACKATHON_API_KEY",
    "OPENROUTER_API_KEY",
    "REQUESTY_API_KEY",
    "OPENCODE_API_KEY",
)


def eval_profile(route: str, tier: CostPolicyTier) -> TaskProfile:
    """Selection profile for one eval route: synthetic coding, tier-capped."""
    return TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        required_capabilities=frozenset({TaskCapability.CHAT}),
        quality_threshold=QualityThreshold.STANDARD,
        cost_policy_tier=tier,
        user_backend_override=route,
    )


def catalog_order(
    route: str, catalog: tuple, tier: CostPolicyTier, max_candidates: int
) -> list[str]:
    """Catalog-preferred model ids: recommended first, then alternatives."""
    try:
        recommendation = recommend_model(eval_profile(route, tier), catalog)
    except ValueError:
        return []
    ordered = [recommendation.selected.backend.model]
    ordered.extend(entry.backend.model for entry in recommendation.alternatives)
    seen: list[str] = []
    for model in ordered:
        if model not in seen:
            seen.append(model)
    return seen[: max(0, max_candidates)]


def recent_failed_models(snapshot_dir: Path, *, limit_files: int = 5) -> set[tuple[str, str]]:
    """(route, model) pairs with transport errors in the newest snapshots."""
    try:
        files = sorted(snapshot_dir.glob("route-eval-*.json"))[-limit_files:]
    except OSError:
        return set()
    failed: set[tuple[str, str]] = set()
    for path in files:
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            route, model, error = row.get("route"), row.get("model"), row.get("error")
            if error and isinstance(route, str) and isinstance(model, str) and model != "?":
                failed.add((route, model))
    return failed


def resolve_route(
    route: str,
    *,
    catalog: tuple,
    credentials: dict[str, str | None],
    allow_tier: CostPolicyTier,
    max_candidates: int,
    skip: frozenset[tuple[str, str]],
    live_refresh: bool,
) -> tuple[list[str], str]:
    """Resolve ordered candidates for one route; tier-blocked returns []."""
    ceiling = ROUTE_TIERS[route]
    if not cost_policy_allows(ceiling, allow_tier):
        return [], f"tier-blocked: route needs {ceiling.value}, run allows {allow_tier.value}"
    tier = ceiling if ceiling == CostPolicyTier.FREE_ONLY else allow_tier
    preferred = catalog_order(route, catalog, tier, max_candidates)
    if route in FREE_ROUTES and live_refresh:
        live = [
            model
            for model in route_eval.list_free_candidates(route, credentials)
            if (route, model) not in skip
        ]
        ordered = [model for model in preferred if model in live]
        ordered.extend(model for model in live if model not in ordered)
        ordered.extend(
            model for model in preferred if model not in live and (route, model) not in skip
        )
        skipped = sorted(model for failed_route, model in skip if failed_route == route)
        note = f"catalog={preferred} live={live} skipped={skipped}"
        return ordered[: max(0, max_candidates)], note
    note = f"catalog={preferred} live-refresh={'off' if route in FREE_ROUTES else 'n/a'}"
    return preferred, note


def apply_tier_blocks(
    results: list[EvalResult], blocked: dict[str, str], gate: str
) -> list[EvalResult]:
    """Rewrite no-model skips as tier-blocked rows for blocked routes."""
    rewritten = []
    for item in results:
        if item.route in blocked and item.error == "no-model":
            rewritten.append(
                EvalResult(
                    item.route,
                    "?",
                    item.checked_utc,
                    False,
                    None,
                    None,
                    None,
                    blocked[item.route],
                    task_id=gate,
                )
            )
        else:
            rewritten.append(item)
    return rewritten


def write_resolution_record(
    resolutions: dict[str, dict[str, object]], snapshot_dir: Path, allow_tier: CostPolicyTier
) -> Path:
    """Write the candidate-resolution audit record next to the snapshot."""
    import time

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = snapshot_dir / f"ladder-resolved-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "generated_utc": datetime.datetime.now(datetime.UTC).isoformat(),
                "allow_tier": allow_tier.value,
                "routes": resolutions,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    """CLI mirroring route_eval plus catalog and tier policy flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=Path("artifacts/route-evals"))
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("packages/ai_orchestrator/examples/model_catalog.toml"),
        help="orchestrator model catalog (default: example catalog)",
    )
    parser.add_argument(
        "--allow-tier",
        default=CostPolicyTier.PREPAID_CREDITS_ALLOWED.value,
        choices=[tier.value for tier in CostPolicyTier],
        help="run cost allowance; routes above it are tier-blocked (default: prepaid)",
    )
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
    parser.add_argument(
        "--max-output-tokens",
        nargs="*",
        default=None,
        metavar="TASK:N",
        help="per-task output cap overrides, e.g. T3:16384 (default: task specs)",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=3,
        help="walk attempts per route before moving on (default: 3)",
    )
    parser.add_argument(
        "--no-live-refresh",
        action="store_true",
        help="resolve free routes from catalog pins only (default: live $0 refresh)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Resolve candidates per route, walk the ladder, write snapshots."""
    parser = build_parser()
    args = parser.parse_args(argv)
    tasks = tuple(args.tasks) if args.tasks is not None else TASKS
    unknown = [task for task in tasks if task not in TASK_SPECS]
    if unknown:
        parser.error(f"unknown task id(s): {', '.join(unknown)} (choose from {' '.join(TASKS)})")
    gate = tasks[0] if tasks else "T0"
    try:
        overrides = route_eval.parse_output_overrides(args.max_output_tokens)
    except ValueError as exc:
        parser.error(str(exc))
    if args.max_candidates < 1:
        parser.error("--max-candidates must be at least 1")
    try:
        catalog = load_model_catalog(args.catalog)
    except (OSError, ValueError) as exc:
        parser.error(f"bad --catalog file {args.catalog}: {exc}")
    allow_tier = CostPolicyTier(args.allow_tier)
    wanted = args.routes or list(EVAL_ROUTES)
    unknown_routes = [route for route in wanted if route not in EVAL_ROUTES]
    if unknown_routes:
        parser.error(f"unknown route(s): {', '.join(unknown_routes)}")
    load_dotenv()
    credentials = {name: os.getenv(name) or None for name in CREDENTIAL_NAMES}
    skip = frozenset(recent_failed_models(args.snapshot_dir))
    resolutions: dict[str, dict[str, object]] = {}
    blocked: dict[str, str] = {}
    models: dict[str, list[str]] = {}
    for route in EVAL_ROUTES:
        if route not in wanted:
            continue
        candidates, note = resolve_route(
            route,
            catalog=catalog,
            credentials=credentials,
            allow_tier=allow_tier,
            max_candidates=args.max_candidates,
            skip=skip,
            live_refresh=not args.no_live_refresh,
        )
        resolutions[route] = {"candidates": candidates, "note": note}
        if not candidates and note.startswith("tier-blocked"):
            blocked[route] = note
        models[route] = candidates
    results = route_eval.run_all(
        credentials,
        tasks=tasks,
        models=models,
        routes=wanted,
        max_attempts=args.max_candidates,
        stop_on_fail=not args.continue_past_fail,
        max_output_tokens=overrides,
    )
    results = apply_tier_blocks(results, blocked, gate)
    snapshot = route_eval.write_results_snapshot(results, tasks, args.snapshot_dir)
    record = write_resolution_record(resolutions, args.snapshot_dir, allow_tier)
    for item in results:
        print(item.summary())
    print(f"snapshot: {snapshot}")
    print(f"resolved: {record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
