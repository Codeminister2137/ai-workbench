"""Compose builder: locked-down services, internal network, valid YAML."""

from __future__ import annotations

import json

import pytest
from docker_compose import ComposeSpec, build_project, compose_file_content

yaml = pytest.importorskip("yaml")


@pytest.fixture
def spec(tmp_path):
    module = tmp_path / "inference_proxy.py"
    module.write_text("# stub\n", encoding="utf-8")
    return ComposeSpec(
        run_id="r1",
        project_name="proof-r1",
        proxy_token="t" * 40,
        proxy_module_host_path=module,
        workspace_host_path=tmp_path / "ws",
        result_host_path=tmp_path / "res",
    )


def test_services_locked_down_and_internal(spec) -> None:
    doc = build_project(spec)
    assert doc["networks"]["inference"]["internal"] is True
    assert "gateway_mode_ipv4" in json.dumps(doc["networks"])
    for name in ("proxy", "worker"):
        service = doc["services"][name]
        assert service["networks"] == ["inference"]
        assert service["user"] == "65532:65532"
        assert service["cap_drop"] == ["ALL"]
        assert service["read_only"] is True
        assert "never" in (service["image"], service["pull_policy"])
    assert "sha256:" in doc["services"]["proxy"]["image"]
    assert doc["services"]["proxy"]["environment"]["PROXY_TOKEN"] == "t" * 40


@pytest.fixture
def spec_with_command(spec):
    from docker_compose import ComposeSpec

    return ComposeSpec(
        run_id=spec.run_id,
        project_name=spec.project_name,
        proxy_token=spec.proxy_token,
        proxy_module_host_path=spec.proxy_module_host_path,
        worker_command=("python", "-c", "import json\ndef check():\n    pass\n"),
    )


def test_short_token_and_missing_module_refused(spec, tmp_path) -> None:
    bad_token = ComposeSpec(
        run_id="r1",
        project_name="p",
        proxy_token="short",
        proxy_module_host_path=tmp_path / "inference_proxy.py",
    )
    with pytest.raises(ValueError, match="at least 32"):
        build_project(bad_token)
    no_module = ComposeSpec(run_id="r1", project_name="p", proxy_token="t" * 40)
    with pytest.raises(ValueError, match="host path"):
        build_project(no_module)


def test_rendered_yaml_round_trips(spec) -> None:
    text = compose_file_content(spec)
    assert "do not hand-edit" in text
    doc = yaml.safe_load(text)
    assert doc["networks"]["inference"]["internal"] is True
    assert doc["services"]["proxy"]["environment"]["PROXY_RUN_ID"] == "r1"
    assert "/result:rw" in str(doc["services"]["worker"].get("volumes"))


def test_multiline_programs_survive_yaml_escaping(spec_with_command) -> None:
    text = compose_file_content(spec_with_command)
    doc = yaml.safe_load(text)
    command = doc["services"]["worker"]["command"]
    program = command[-1]
    assert "import json" in program and "\ndef check(" in program
    compile(program, "<worker>", "exec")
