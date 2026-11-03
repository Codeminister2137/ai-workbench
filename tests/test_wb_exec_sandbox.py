"""Workbench exec-sandbox + snapshot-replay regression tests (2026-11-03 fix).

Part 1 -- route_eval grades model text in a subprocess sandbox: a dunder
escape that breaks the old builtins-stripped in-process exec cannot touch
parent-process state (modules, globals, environment) through the new API,
and legitimate answers still grade the same.

Part 2 -- day_cycle replays only allowlisted argv lists: legacy strings,
tampered snapshot entries, and non-allowlisted commands are refused and
never executed, and every launch echoes its exact command line first.

No test here launches a real service, touches the network, or runs day_cycle.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from ai_provider import route_eval

DAY_CYCLE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/day_cycle.py"
_spec = importlib.util.spec_from_file_location("day_cycle_wb", DAY_CYCLE_SCRIPT)
assert _spec is not None and _spec.loader is not None
day_cycle = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = day_cycle
_spec.loader.exec_module(day_cycle)

_ESCAPE_BODY = (
    "try:\n"
    "    for _c in ().__class__.__base__.__subclasses__():\n"
    "        try:\n"
    "            _g = _c.__init__.__globals__\n"
    "        except:\n"
    "            continue\n"
    "        try:\n"
    "            _s = _g.get('sys')\n"
    "        except:\n"
    "            continue\n"
    "        if _s is None:\n"
    "            continue\n"
    "        try:\n"
    "            _s.modules['os'].environ['WB_SANDBOX_PWNED'] = 'pwned'\n"
    "        except:\n"
    "            pass\n"
    "        try:\n"
    "            _m = _s.modules.get('ai_provider.route_eval')\n"
    "            if _m is not None:\n"
    "                _m.check_completion.__globals__['WB_SANDBOX_PWNED'] = 'pwned'\n"
    "        except:\n"
    "            pass\n"
    "except:\n"
    "    pass\n"
)
"""Classic subclasses->sys->os chain; needs no builtins and no imports."""

_PROBE_BODY = (
    "_REACHED_OS_NAME = None\n"
    "for _c in ().__class__.__base__.__subclasses__():\n"
    "    try:\n"
    "        _g = _c.__init__.__globals__\n"
    "    except:\n"
    "        continue\n"
    "    if _g.get('sys') is None:\n"
    "        continue\n"
    "    _REACHED_OS_NAME = _g.get('sys').modules['os'].name\n"
    "    break\n"
)

_T1_SOLUTION = (
    "def clamp(value, lo, hi):\n"
    "    if value < lo:\n"
    "        return lo\n"
    "    if value > hi:\n"
    "        return hi\n"
    "    return value\n"
    "def retry_delay_ms(base_ms, factor, attempt):\n"
    "    return base_ms * factor ** attempt\n"
)

_T0_ESCAPE = "```python\ndef add2(x):\n    return x + 2\n" + _ESCAPE_BODY + "```"
_T1_ESCAPE = "```python\n" + _T1_SOLUTION + _ESCAPE_BODY + "```"


def test_escape_primitive_reaches_os_in_bare_exec() -> None:
    """The attack primitive works: dunder traversal reaches os with no builtins.

    This is what the old in-process grader allowed; it must keep working
    here so the sandbox test below is not vacuous. The snippet is a fixed
    test constant, never model output.
    """
    probe = "def add2(x):\n    return x + 2\n" + _PROBE_BODY
    namespace = {"__builtins__": {}}
    exec(compile(probe, "<probe>", "exec"), namespace)  # noqa: B102 - fixed test constant
    assert namespace["_REACHED_OS_NAME"] == os.name


@pytest.mark.parametrize(
    ("check", "payload"),
    [
        (route_eval.check_completion, _T0_ESCAPE),
        (route_eval.check_t1, _T1_ESCAPE),
    ],
)
def test_dunder_escape_cannot_touch_parent_state(check, payload, monkeypatch) -> None:
    """A dunder escape in model text cannot reach parent-process state.

    The payload defines a correct answer (so it grades True) while trying
    to set parent env and a parent module global. Both must stay clean.
    """
    monkeypatch.delenv("WB_SANDBOX_PWNED", raising=False)
    assert "WB_SANDBOX_PWNED" not in vars(route_eval)
    try:
        assert check(payload) is True
        assert os.environ.get("WB_SANDBOX_PWNED") is None
        assert "WB_SANDBOX_PWNED" not in vars(route_eval)
    finally:
        vars(route_eval).pop("WB_SANDBOX_PWNED", None)


def test_replay_allows_known_module_script_and_ollama() -> None:
    """Allowlisted service commands replay; nothing launches here."""
    cwd = day_cycle.REPO_ROOT
    assert day_cycle.is_replay_allowed(
        "operator", ["python", "-m", "remote_operator.cli", "serve"], cwd
    )
    assert day_cycle.is_replay_allowed("dashboard", ["python", "scripts/day_cycle.py", "open"], cwd)
    assert day_cycle.is_replay_allowed("ollama", ["ollama", "serve"], cwd)


def test_replay_refuses_dangerous_commands(tmp_path: Path) -> None:
    """-c, bare -, foreign modules, planted interpreters, and escapes refuse."""
    cwd = day_cycle.REPO_ROOT
    planted = str(tmp_path / "python.exe")
    outside = str(tmp_path / "evil.py")
    assert not day_cycle.is_replay_allowed("operator", ["python", "-c", "print(1)"], cwd)
    assert not day_cycle.is_replay_allowed("operator", ["python", "-"], cwd)
    assert not day_cycle.is_replay_allowed("operator", ["python", "-m", "os", "serve"], cwd)
    assert not day_cycle.is_replay_allowed("operator", [planted, "-m", "remote_operator.cli"], cwd)
    assert not day_cycle.is_replay_allowed("operator", ["python", outside], cwd)
    assert not day_cycle.is_replay_allowed("ollama", ["ollama", "run", "x"], cwd)
    assert not day_cycle.is_replay_allowed("operator", [], cwd)


def test_replay_argv_for_refuses_legacy_and_tampered() -> None:
    """Legacy strings and non-allowlisted snapshots refuse with a reason."""
    cwd = day_cycle.REPO_ROOT
    argv, reason = day_cycle.replay_argv_for("operator", 8765, {"8765": ["python", "-c", "x"]}, cwd)
    assert argv is None and "allowlist" in reason
    argv, reason = day_cycle.replay_argv_for("operator", 8765, {"8765": "python -m x"}, cwd)
    assert argv is None and "argv list" in reason
    argv, reason = day_cycle.replay_argv_for("operator", 8765, {}, cwd)
    assert argv is None and reason == "missing"
