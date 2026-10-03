"""Offline contracts for verified profile counting and conservative refusal."""

import hashlib
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from ai_provider import research_token_count as counter
from ai_provider.contracts import AIMessage, AIRequest, MessageRole


@pytest.fixture
def profile(tmp_path, monkeypatch):
    asset = tmp_path / "tokenizer.json"
    asset.write_bytes(b"{}")
    template = "inspected template\r\n"
    monkeypatch.setitem(
        counter.TEMPLATE_SHA256, "qwen3:14b", hashlib.sha256(template.encode()).hexdigest()
    )
    monkeypatch.setitem(counter.TOKENIZER_SHA256, "qwen3:14b", hashlib.sha256(b"{}").hexdigest())
    info = {"template": template, "modelfile": "FROM /models/" + counter.MODEL_BLOB["qwen3:14b"]}
    request = AIRequest(
        (
            AIMessage(MessageRole.SYSTEM, "Grounding rules"),
            AIMessage(MessageRole.USER, "Full report and source 🐍\r\n" * 2000),
        ),
        model="qwen3:14b",
        metadata={"ollama_thinking": True},
    )
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
            assert request.messages[1].content in value
            assert " /think<|im_end|>" in value
            assert add_special_tokens is False
            assert events == ["no_truncation", "no_padding"]
            events.append("encoded_full_input")
            return SimpleNamespace(ids=[1, 2, 3])

    library = SimpleNamespace(Tokenizer=Tokenizer, __version__=counter.TOKENIZERS_VERSION)
    monkeypatch.setitem(sys.modules, "tokenizers", library)
    return asset, info, request, events, library


def test_complete_verified_evidence_is_counted_without_padding_or_truncation(profile):
    asset, info, request, events, _ = profile
    assert counter.count_review_input_tokens(request, info, asset, runtime_version="0.32.5") == 3
    assert events[-1] == "encoded_full_input"


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "model",
        "blob",
        "template",
        "renderer",
        "system",
        "asset",
        "native_default",
        "dependency",
        "library_version",
        "history",
        "missing_asset",
        "date_dependent",
        "model_history",
        "model_adapter",
    ],
)
def test_unverified_inputs_are_refused_without_encoding(profile, monkeypatch, change):
    asset, info, request, events, library = profile
    version = "0.32.5"
    if change == "version":
        version = "0.32.6"
    elif change == "model":
        request = replace(request, model="other")
    elif change == "blob":
        info["modelfile"] = "FROM /models/changed"
    elif change == "template":
        info["template"] = "changed"
    elif change == "renderer":
        info["renderer"] = "alternate"
    elif change == "system":
        info["system"] = "Extra default instructions"
    elif change == "asset":
        asset.write_bytes(b"changed")
    elif change == "native_default":
        request = replace(request, metadata={})
    elif change == "dependency":
        monkeypatch.setitem(sys.modules, "tokenizers", None)
    elif change == "library_version":
        library.__version__ = "other"
    elif change == "history":
        request = replace(
            request, messages=request.messages + (AIMessage(MessageRole.USER, "extra"),)
        )
    elif change == "missing_asset":
        asset = asset.with_name("missing.json")
    elif change == "model_history":
        info["modelfile"] += '\nMESSAGE user "previous turn"'
    elif change == "model_adapter":
        info["modelfile"] += "\nADAPTER /models/unverified"
    else:
        request = replace(request, model="gpt-oss:20b")
    with pytest.raises(ValueError):
        counter.count_review_input_tokens(request, info, asset, runtime_version=version)
    assert not events
