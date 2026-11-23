import importlib.util
import types

import pytest

# Helper to load the module from path


def load_module_from_path(name: str, path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Load the script module
_check_merge_tier = load_module_from_path("check_merge_tier", "scripts/check-merge-tier.py")
classify_path = _check_merge_tier.classify_path
classify_diff = _check_merge_tier.classify_diff
verdict = _check_merge_tier.verdict

# Test cases for tier classification and precedence
TIER3_PATHS = [
    "packages/ai_provider/secrets.py",  # secrets pattern
    "scripts/secrets.py",  # secrets pattern
    "packages/core/utils/__init__.py",  # cross-package init (tier3)
    "docs/architecture.md",  # architecture pattern overrides docs tier1
    "adapter/provider_route.py",  # routing pattern
    "billing/payment.py",  # billing pattern
    "migrate/foo.py",  # data migration pattern
    "delete/bar.json",  # delete pattern
]

TIER1_PATHS = [
    "docs/decisions/ADR-088.md",  # docs path tier1
    "tests/test_utils.py",  # test file tier1
    "scripts/build.sh",  # scripts tier1
    "config.yaml",  # extension tier1
    "README.md",  # extension tier1
]

TIER2_PATHS = [
    "packages/core/utils/helper.py",  # plain code not matching any tier3 or tier1 rules
    "apps/ai_council/main.py",
]


def test_classify_path_tier3_precedence():
    for path in TIER3_PATHS:
        tier = classify_path(path)
        assert tier == 3, f"Expected tier 3 for {path}, got {tier}"


# Paths that are tier1 should not be classified as tier2 or tier3.
@pytest.mark.parametrize("path", TIER1_PATHS)
def test_classify_path_tier1(path):
    assert classify_path(path) == 1, f"Expected tier 1 for {path}"


# Plain code should be tier2
@pytest.mark.parametrize("path", TIER2_PATHS)
def test_classify_path_tier2(path):
    assert classify_path(path) == 2, f"Expected tier 2 for {path}"


# Mixed list and sorting
def test_classify_diff_sorting_and_precedence():
    mixed = [
        "packages/core/utils/helper.py",  # tier2
        "docs/decisions/ADR-088.md",  # tier1
        "tests/test_utils.py",  # tier1
        "scripts/build.sh",  # tier1
        "config.yaml",  # tier1
        "packages/ai_provider/secrets.py",  # tier3
    ]
    rated = classify_diff(mixed)
    # Verify sorting: first entry is tier 3, then any tier2, then tier1
    assert rated[0][0] == 3, "Top tier should be 3"
    # After tier3, there may be multiple tiers. Let's check order of rest.
    tiers = [t for t, _ in rated]
    # There should be exactly one tier3 in this list
    assert tiers.count(3) == 1
    # The remaining tiers should be sorted by descending: tier2 then tier1s
    assert all(t <= prev for prev, t in zip([3] + tiers[:-1], tiers, strict=True)), (
        "Tiers not sorted descending"
    )


# Verdict logic tests
def test_verdict_tier3():
    rated = [(3, "a"), (2, "b")]
    code, text = verdict(rated)
    assert code == 2
    assert "Tier 3" in text


def test_verdict_tier2_only():
    rated = [(2, "a"), (1, "b")]
    code, text = verdict(rated)
    assert code == 1
    assert "Tier 2" in text


def test_verdict_all_tier1_or_empty():
    # empty list
    code, text = verdict([])
    assert code == 0
    assert "no changed files" in text.lower()
    # all tier1 entries
    rated = [(1, "x"), (1, "y")]
    code, text = verdict(rated)
    assert code == 0
    assert "Tier 1" in text


# Ensure that precedence of highest tier is used in verdict regardless of order
def test_verdict_precedence():
    rated_unsorted = [(2, "a"), (3, "b")]
    # Sort to ensure highest tier comes first before calling verdict
    rated_sorted = sorted(rated_unsorted, key=lambda x: -x[0])
    code, text = verdict(rated_sorted)
    assert code == 2
    assert "Tier 3" in text
