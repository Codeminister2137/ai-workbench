import pytest
from investor.guards import (
    PaperGuardError,
    check_cost,
    check_endpoint,
    check_paper_credentials,
)


def test_paper_endpoint_passes_and_returns_host():
    assert check_endpoint("https://paper-api.alpaca.markets/v2/orders?x=1") == (
        "paper-api.alpaca.markets"
    )
    assert check_endpoint("https://PAPER-API.ALPACA.MARKETS/v2") == "paper-api.alpaca.markets"
    assert check_endpoint("HTTPS://paper-api.alpaca.markets/v2") == "paper-api.alpaca.markets"
    assert check_endpoint("https://paper-api.alpaca.markets:443/v2") == "paper-api.alpaca.markets"


@pytest.mark.parametrize(
    ("url", "match"),
    [
        ("https://api.alpaca.markets/v2/orders", "live"),
        ("http://paper-api.alpaca.markets/v2", "https"),
        ("https://data.alpaca.markets/v2/stocks", "allowlist"),
        ("https://evil.example.com/v2", "allowlist"),
        ("https://user:pass@paper-api.alpaca.markets/v2", "credentials"),
        ("https://paper-api.alpaca.markets:8443/v2", "port"),
        ("https://127.0.0.1/v2", "allowlist"),
        ("https://[::1]/v2", "allowlist"),
        ("https:///v2", "host missing"),
        ("not a url", "https"),
        ("", "https"),
    ],
)
def test_endpoint_refusals(url, match):
    with pytest.raises(PaperGuardError, match=match):
        check_endpoint(url)


def test_paper_credentials_pass():
    check_paper_credentials(
        key_id="PKABC",
        key_source="ALPACA_PAPER_KEY_ID",
        secret="s3cret",
        secret_source="ALPACA_PAPER_SECRET",
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"key_source": "ALPACA_KEY_ID"},
        {"secret_source": "ALPACA_SECRET"},
        {"key_source": "ALPACA_LIVE_KEY_ID"},
        {"key_id": ""},
        {"key_id": "   "},
        {"secret": ""},
    ],
)
def test_credential_refusals(patch):
    args = {
        "key_id": "PKABC",
        "key_source": "ALPACA_PAPER_KEY_ID",
        "secret": "s3cret",
        "secret_source": "ALPACA_PAPER_SECRET",
    }
    args.update(patch)
    with pytest.raises(PaperGuardError):
        check_paper_credentials(**args)


def test_cost_boundaries():
    check_cost(notional=99.0, max_notional=100.0, fees=1.0)
    check_cost(notional=100.0, max_notional=100.0)
    check_cost(notional=0.0, max_notional=100.0)
    with pytest.raises(PaperGuardError, match="exceeds cap"):
        check_cost(notional=99.0, max_notional=100.0, fees=1.01)


@pytest.mark.parametrize(
    "args",
    [
        {"notional": -1.0, "max_notional": 100.0},
        {"notional": 10.0, "max_notional": 100.0, "fees": -0.5},
        {"notional": float("nan"), "max_notional": 100.0},
        {"notional": float("inf"), "max_notional": 100.0},
        {"notional": 10.0, "max_notional": 0.0},
        {"notional": 10.0, "max_notional": -5.0},
        {"notional": True, "max_notional": 100.0},
        {"notional": "10", "max_notional": 100.0},
    ],
)
def test_cost_refusals(args):
    with pytest.raises(PaperGuardError):
        check_cost(**args)
