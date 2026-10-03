import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_probe():
    path = Path(__file__).parents[1] / "scripts" / "research-token-count-prototype.py"
    spec = importlib.util.spec_from_file_location("token_count_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_preserves_complete_text_disables_padding_and_truncation(tmp_path, monkeypatch):
    events = []

    class Tokenizer:
        @classmethod
        def from_str(cls, value):
            assert value == "{}"
            return cls()

        def no_truncation(self):
            events.append("no_truncation")

        def no_padding(self):
            events.append("no_padding")

        def encode(self, value, *, add_special_tokens):
            assert value == "full source 🐍\nlast line"
            assert add_special_tokens is False
            assert events == ["no_truncation", "no_padding"]
            return SimpleNamespace(ids=[1, 2, 3])

    monkeypatch.setitem(
        sys.modules, "tokenizers", SimpleNamespace(Tokenizer=Tokenizer, __version__="test")
    )
    tokenizer = tmp_path / "tokenizer.json"
    tokenizer.write_text("{}", encoding="utf-8")
    prompt = tmp_path / "rendered.txt"
    prompt.write_bytes("full source 🐍\nlast line".encode())
    result = load_probe().count_rendered_prompt(tokenizer, prompt)
    assert result["token_count"] == 3
    assert result["runtime_compatibility"] == "UNVERIFIED"
    assert result["production_admission_changed"] is False
    assert len(result["rendered_prompt_sha256"]) == 64


def test_missing_dependency_is_reported_without_installing(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "tokenizers", None)
    tokenizer = tmp_path / "tokenizer.json"
    tokenizer.write_text("{}", encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("public text", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        load_probe().main(
            ["--tokenizer-file", str(tokenizer), "--rendered-prompt-file", str(prompt)]
        )
    assert error.value.code == 2
    assert "approve installation separately" in capsys.readouterr().err


def review_request(model="qwen3:14b", thinking=None):
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "Evidence rules  \n完整"},
            {"role": "user", "content": "Full report  \nFinal source passage 🐍"},
        ],
        "metadata": {} if thinking is None else {"ollama_thinking": thinking},
        "tools": [],
    }


@pytest.mark.parametrize("thinking, suffix", [(True, " /think"), (False, " /no_think")])
def test_qwen_preserves_full_messages_and_explicit_thinking_framing(thinking, suffix):
    probe = load_probe()
    request = review_request(thinking=thinking)
    rendered = probe.render_research_review_prompt(
        request, template_sha256=probe.TEMPLATE_SHA256[request["model"]]
    )
    assert request["messages"][0]["content"] in rendered
    assert request["messages"][1]["content"] + suffix + "<|im_end|>" in rendered
    assert rendered.startswith("<|im_start|>system\n\n")
    assert rendered.endswith("<think>\n\n</think>\n\n") is (thinking is False)


@pytest.mark.parametrize("thinking, effort", [(None, "medium"), ("high", "high")])
def test_gpt_oss_uses_explicit_runtime_date_and_complete_instruction_channel(thinking, effort):
    probe = load_probe()
    request = review_request("gpt-oss:20b", thinking)
    rendered = probe.render_research_review_prompt(
        request, template_sha256=probe.TEMPLATE_SHA256[request["model"]], current_date="2026-10-03"
    )
    assert "Current date: 2026-10-03" in rendered
    assert "Reasoning: " + effort in rendered
    assert (
        "<|start|>developer<|message|>\n\n# Instructions\n\n" + request["messages"][0]["content"]
        in rendered
    )
    assert request["messages"][1]["content"] in rendered
    assert rendered.endswith("<|start|>assistant")


@pytest.mark.parametrize(
    "change",
    [
        "tools",
        "history",
        "image",
        "wrong_role",
        "invalid_model",
        "numeric_thinking",
        "gpt_boolean",
        "empty_system",
    ],
)
def test_unsupported_counting_shapes_fail_closed(change):
    probe = load_probe()
    request = review_request()
    if change == "tools":
        request["tools"] = [{"name": "fetch"}]
    elif change == "history":
        request["messages"].append({"role": "assistant", "content": "Previous"})
    elif change == "image":
        request["messages"][1]["images"] = ["ignored image"]
    elif change == "wrong_role":
        request["messages"][0]["role"] = "developer"
    elif change == "invalid_model":
        request["model"] = []
    elif change == "numeric_thinking":
        request["metadata"]["ollama_thinking"] = 1
    elif change == "gpt_boolean":
        request = review_request("gpt-oss:20b", True)
    else:
        request["messages"][0]["content"] = ""
    with pytest.raises(ValueError):
        probe.render_research_review_prompt(
            request,
            template_sha256=probe.TEMPLATE_SHA256.get(
                request["model"] if isinstance(request["model"], str) else "", ""
            ),
            current_date="2026-10-03",
        )


def test_unrecognized_template_and_missing_runtime_date_are_refused():
    probe = load_probe()
    with pytest.raises(ValueError, match="fingerprint"):
        probe.render_research_review_prompt(review_request(), template_sha256="changed")
    with pytest.raises(ValueError, match="exact runtime date"):
        probe.render_research_review_prompt(
            review_request("gpt-oss:20b"), template_sha256=probe.TEMPLATE_SHA256["gpt-oss:20b"]
        )


def test_qwen_native_default_framing_is_refused_instead_of_approximated():
    probe = load_probe()
    with pytest.raises(ValueError, match="native default is unverified"):
        probe.render_research_review_prompt(
            review_request(), template_sha256=probe.TEMPLATE_SHA256["qwen3:14b"]
        )


def test_request_counter_rejects_wrong_tokenizer_before_import(tmp_path, monkeypatch):
    probe = load_probe()
    template = tmp_path / "template.txt"
    template.write_bytes(b"known template")
    monkeypatch.setitem(
        probe.TEMPLATE_SHA256, "qwen3:14b", hashlib.sha256(template.read_bytes()).hexdigest()
    )
    tokenizer = tmp_path / "tokenizer.json"
    tokenizer.write_bytes(b"{}")
    request = tmp_path / "request.json"
    request.write_text(json.dumps(review_request(thinking=True)), encoding="utf-8")
    monkeypatch.setitem(sys.modules, "tokenizers", None)
    with pytest.raises(ValueError, match="Tokenizer asset"):
        probe.count_review_request(tokenizer, request, template)


def test_request_counter_counts_complete_fingerprinted_rendering(tmp_path, monkeypatch):
    probe = load_probe()
    template = tmp_path / "template.txt"
    template.write_bytes(b"inspected template\r\n")
    tokenizer = tmp_path / "tokenizer.json"
    tokenizer.write_bytes(b"{}")
    monkeypatch.setitem(
        probe.TEMPLATE_SHA256, "qwen3:14b", hashlib.sha256(template.read_bytes()).hexdigest()
    )
    monkeypatch.setitem(
        probe.TOKENIZER_SHA256, "qwen3:14b", hashlib.sha256(tokenizer.read_bytes()).hexdigest()
    )
    request_data = review_request(thinking=False)
    request = tmp_path / "request.json"
    request.write_text(json.dumps(request_data), encoding="utf-8")
    rendered = probe.render_research_review_prompt(
        request_data, template_sha256=probe.TEMPLATE_SHA256["qwen3:14b"]
    )
    calls = []

    class Tokenizer:
        @classmethod
        def from_str(cls, value):
            assert value == "{}"
            return cls()

        def no_truncation(self):
            calls.append("no_truncation")

        def no_padding(self):
            calls.append("no_padding")

        def encode(self, value, *, add_special_tokens):
            assert calls == ["no_truncation", "no_padding"]
            assert value == rendered
            assert add_special_tokens is False
            return SimpleNamespace(ids=[7, 8, 9, 10])

    monkeypatch.setitem(
        sys.modules, "tokenizers", SimpleNamespace(Tokenizer=Tokenizer, __version__="test")
    )
    result = probe.count_review_request(tokenizer, request, template)
    assert result["token_count"] == 4
    assert result["rendered_prompt_sha256"] == hashlib.sha256(rendered.encode()).hexdigest()
    assert result["template_sha256"] == hashlib.sha256(template.read_bytes()).hexdigest()
    assert result["runtime_compatibility"] == "UNVERIFIED"
    assert result["production_admission_changed"] is False
