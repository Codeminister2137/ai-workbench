"""Free API transport failures preserve real shared effects and routing bounds."""

import json
from urllib.parse import urlsplit

import pytest
from ai_agent import repo_coding_assistant as cli


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


@pytest.mark.parametrize(
    "code,continues,free_tier,cache_price_changes",
    [
        (402, True, False, False),
        (429, True, False, False),
        (400, False, False, False),
        (402, False, True, False),
        (402, False, False, True),
    ],
)
def test_free_provider_failure_preserves_partial_edits_and_complete_instructions(
    tmp_path, monkeypatch, capsys, code, continues, free_tier, cache_price_changes
):
    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        "\n".join(
            f'''[[models]]
route_id = "{route}"
provider = "{provider}"
product = "{product}"
model = "{model}"
location = "external"
access_method = "provider_api"
auth_method = "api_key"
billing_source = "{billing}"
cost_policy_tier = "{tier}"
quality = "standard"
latency = "interactive"
[models.capabilities]
chat = true
tools = true
[models.context_limits]
context_window_tokens = 262144
'''
            for route, provider, product, model, billing, tier in (
                (
                    "primary",
                    "openrouter",
                    "openrouter_free",
                    "google/gemma-4-31b-it:free",
                    "openrouter_free",
                    "free_only",
                ),
                (
                    "secondary",
                    "requesty",
                    "requesty_free",
                    "google/gemma-4-31b-it",
                    "requesty_billing",
                    "free_only",
                ),
                (
                    "paid",
                    "openai",
                    "openai_api",
                    "paid-model",
                    "openai_api_billing",
                    "billing_allowed",
                ),
            )
        ),
        encoding="utf-8",
    )
    instructions = (
        "Inspect current source before changing it; preserve protected.txt.\n"
        + "Public toy rule.\n" * 400
    )
    (tmp_path / "AGENTS.md").write_text(instructions, encoding="utf-8")
    protected = tmp_path / "protected.txt"
    protected.write_text("Independent oracle: value must finish at 2.\n")
    protected_before = protected.read_bytes()
    source = tmp_path / "source.py"
    source.write_text("value = 0\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-only")
    monkeypatch.setenv("REQUESTY_API_KEY", "synthetic-only")
    counts = {"openrouter.ai": 0, "router.requesty.ai": 0}
    pricing_reads = {host: 0 for host in counts}
    observed = []

    def transport(request, **kwargs):
        host = urlsplit(request.full_url).hostname
        assert host in counts, "Unexpected provider or billing path"
        if request.get_method() == "GET":
            if host == "openrouter.ai":
                if request.full_url.endswith("/key"):
                    return Response(
                        {
                            "data": {
                                "is_free_tier": free_tier,
                                "free_model_daily_requests": {
                                    "used": 0,
                                    "limit": 50,
                                    "remaining": 50,
                                },
                            }
                        }
                    )
                pricing_reads[host] += 1
                return Response(
                    {
                        "data": [
                            {
                                "id": "google/gemma-4-31b-it:free",
                                "pricing": {"prompt": "0", "completion": "0"},
                                "supported_parameters": ["tools", "temperature", "top_p"],
                            }
                        ]
                    }
                )
            pricing_reads[host] += 1
            cache_price = 0.01 if cache_price_changes and counts[host] >= 1 else 0
            return Response(
                {
                    "data": [
                        {
                            "id": "google/gemma-4-31b-it",
                            "api": "chat",
                            "input_price": 0,
                            "output_price": 0,
                            "caching_1h_price": cache_price,
                        }
                    ]
                }
            )
        payload = json.loads(request.data)
        assert payload["temperature"] == 1.0 and payload["top_p"] == 0.95
        messages = "\n".join(message.get("content", "") or "" for message in payload["messages"])
        assert instructions.strip() in messages
        assert len(payload["tools"]) == 18
        assert payload["model"] == (
            "google/gemma-4-31b-it:free" if host == "openrouter.ai" else "google/gemma-4-31b-it"
        )
        if host == "openrouter.ai":
            assert payload["provider"]["data_collection"] == "deny"
            assert all(value == 0 for value in payload["provider"]["max_price"].values())
        elif counts[host] == 0:
            assert "Route-failure continuation" in messages
            assert source.read_text() == "value = 1\n"
        index = counts[host]
        expected_values = (0, 0, 1) if host == "openrouter.ai" else (1, 1, 2)
        assert source.read_text() == f"value = {expected_values[index]}\n"
        counts[host] += 1
        observed.append(host)
        if host == "openrouter.ai" and index == 2:
            assert source.read_text() == "value = 1\n"
            return Response({"error": {"code": code, "message": "ignored synthetic remote text"}})
        if index < 2:
            name = "read_file" if index == 0 else "edit_file"
            arguments = (
                {"path": "source.py"}
                if index == 0
                else {
                    "path": "source.py",
                    "old_text": f"value = {0 if host == 'openrouter.ai' else 1}",
                    "new_text": f"value = {1 if host == 'openrouter.ai' else 2}",
                }
            )
            return Response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": f"{host}-{index}",
                                        "type": "function",
                                        "function": {
                                            "name": name,
                                            "arguments": json.dumps(arguments),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            )
        return Response(
            {
                "choices": [
                    {
                        "message": {"content": "Completed synthetic continuation."},
                        "finish_reason": "stop",
                    }
                ]
            }
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", transport)
    monkeypatch.setattr("ai_provider.adapters.openrouter.urlopen", transport)
    monkeypatch.setattr("urllib.request.urlopen", transport)
    status = cli.main(
        [
            "--mode",
            "implement",
            "Set value to 2 in source.py; preserve protected.txt.",
            "--repo-root",
            str(tmp_path),
            "--catalog",
            str(catalog),
            "--route-id",
            "primary",
            "--privacy",
            "public_or_low_risk",
            "--cost-policy",
            "free_only",
            "--quality",
            "standard",
            "--approval-policy",
            "trusted_local",
            "--shared-tools",
            "coding",
            "--native-tools",
            "--skip-prompt-review",
            "--execute",
            "--context-budget-chars",
            "0",
            "--instruction-budget-chars",
            "100000",
            "--max-action-rounds",
            "6",
            "--temperature",
            "1.0",
            "--top-p",
            "0.95",
        ]
    )
    assert status == (0 if continues else 1)
    assert source.read_text() == (
        "value = 0\n" if free_tier else "value = 2\n" if continues else "value = 1\n"
    )
    assert protected.read_bytes() == protected_before
    expected_primary = 0 if free_tier else 3
    expected_secondary = 3 if continues else 1 if cache_price_changes else 0
    assert counts == {"openrouter.ai": expected_primary, "router.requesty.ai": expected_secondary}
    assert (
        observed
        == ["openrouter.ai"] * expected_primary + ["router.requesty.ai"] * expected_secondary
    )
    assert all(pricing_reads[host] >= count for host, count in counts.items())
    output = capsys.readouterr().out
    switched = continues or cache_price_changes
    assert (
        "fallback_switch: primary -> secondary" in output
        if switched
        else "fallback_switch:" not in output
    )
    assert "-> paid" not in output
