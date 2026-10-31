"""Fallback evidence bridge; pure data mapping, no network and no inference."""

from ai_orchestrator.evidence import (
    RouteEvidence,
    merge_probe_eval,
    priority_routes,
    unavailable_routes,
)

CATALOG = (
    "meta/muse-spark-1.3",
    "openrouter/a:free",
    "openrouter/b:free",
    "requesty/nvidia-x",
    "local/other",
)


def test_priority_orders_passed_before_reachable_and_skips_rest():
    evidence = [
        RouteEvidence("openrouter", True, None),
        RouteEvidence("meta", True, True),
        RouteEvidence("requesty", False, None),
        RouteEvidence("local", True, False),
    ]
    assert priority_routes(evidence, CATALOG) == (
        "meta/muse-spark-1.3",
        "openrouter/a:free",
        "openrouter/b:free",
    )
    assert unavailable_routes(evidence, CATALOG) == frozenset({"requesty/nvidia-x"})


def test_unknown_providers_keep_existing_rank_behind():
    assert priority_routes([], CATALOG) == ()
    assert unavailable_routes([], CATALOG) == frozenset()
    assert priority_routes([RouteEvidence("meta", True, True)], CATALOG) == ("meta/muse-spark-1.3",)


def test_merge_joins_probes_with_error_free_evals():
    probes = [
        {"route": "meta", "reachable": True},
        {"route": "requesty", "reachable": True},
        {"route": "broken"},
    ]
    evals = [
        {"route": "meta", "passed": True},
        {"route": "requesty", "passed": False, "error": "ProviderError"},
    ]
    assert merge_probe_eval(probes, evals) == [
        RouteEvidence("meta", True, True),
        RouteEvidence("requesty", True, None),
    ]


def test_eval_only_route_counts_as_reachable():
    merged = merge_probe_eval([], [{"route": "baseten", "passed": True}])
    assert merged == [RouteEvidence("baseten", True, True)]
    assert priority_routes(merged, ("baseten/x",)) == ("baseten/x",)


def test_end_to_end_with_today_snapshot_shape():
    probes = [
        {"route": "meta", "reachable": True},
        {"route": "openrouter", "reachable": True},
        {"route": "ollama", "reachable": False},
    ]
    evals = [
        {"route": "meta", "passed": True},
        {"route": "openrouter", "passed": True},
    ]
    evidence = merge_probe_eval(probes, evals)
    catalog = ("openrouter/a:free", "meta/muse-spark-1.3", "ollama/x", "other/y")
    assert priority_routes(evidence, catalog) == ("openrouter/a:free", "meta/muse-spark-1.3")
    assert unavailable_routes(evidence, catalog) == frozenset({"ollama/x"})
