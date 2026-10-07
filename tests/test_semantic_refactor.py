"""Preview-first Python rename contracts."""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_agent.contracts import ToolCall, ToolCategory
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.shared_approvals import scoped_registry
from ai_agent.tool_profiles import CODING_PROFILE, shared_tool_registry
from ai_agent.tools import ToolContext, default_coding_tools
from ai_agent.tools.refactor import (
    PythonNavigateTool,
    RenameApplyTool,
    RenamePlanStore,
    RenamePreviewTool,
    _jedi_rename,
)


@pytest.fixture
def jedi_required():
    try:
        importlib.import_module("jedi")
    except ImportError:
        pytest.skip("install the optional rename-preview extra for Jedi integration tests")


def package_fixture(root: Path) -> tuple[Path, Path]:
    package = root / "sample_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    source = package / "models.py"
    source.write_text("class Widget:\n    pass\n", encoding="utf-8")
    caller = package / "client.py"
    caller.write_text(
        "from .models import Widget\n\nitem = Widget()\nassert isinstance(item, Widget)\n",
        encoding="utf-8",
    )
    return source, caller


def preview(root: Path, source: Path, line: int, column: int, new_name: str):
    store = RenamePlanStore(root, owner_id="test-owner", task_id="test-task")
    tool = RenamePreviewTool(store)
    result = tool.run(
        ToolCall(
            "rename_preview",
            {
                "path": source.relative_to(root).as_posix(),
                "line": line,
                "column": column,
                "new_name": new_name,
            },
        ),
        ToolContext(root),
    )
    assert not result.is_error, result.output
    return store, result


class TestRenamePreview:
    def test_preview_tracks_imports_and_calls_without_mutating(self, tmp_path, jedi_required):
        source, caller = package_fixture(tmp_path)
        before = {path: path.read_bytes() for path in (source, caller)}
        store, result = preview(tmp_path, source, 1, 7, "Gadget")
        assert all(path.read_bytes() == content for path, content in before.items())
        assert set(result.metadata["files"]) == {
            "sample_pkg/models.py",
            "sample_pkg/client.py",
        }
        assert "class Widget" in result.output and "class Gadget" in result.output
        assert "from .models import Gadget" in result.output
        assert "isinstance(item, Gadget)" in result.output
        assert result.metadata["applied"] is False
        assert store.get(result.metadata["plan_id"], ToolContext(tmp_path)) is not None

    def test_duplicate_names_in_separate_functions_rename_only_selected_binding(
        self, tmp_path, jedi_required
    ):
        source = tmp_path / "scopes.py"
        source.write_text(
            "def first():\n    value = 1\n    return value\n\n"
            "def second():\n    value = 2\n    return value\n",
            encoding="utf-8",
        )
        _, result = preview(tmp_path, source, 2, 5, "first_value")
        assert "first_value = 1" in result.output
        assert "return first_value" in result.output
        assert "-    value = 2" not in result.output
        second_scope = result.output.split(" def second():", maxsplit=1)[1]
        assert "    value = 2" in second_scope
        assert "-    " not in second_scope
        assert "+    " not in second_scope
        assert source.read_text(encoding="utf-8") == (
            "def first():\n    value = 1\n    return value\n\n"
            "def second():\n    value = 2\n    return value\n"
        )

    def test_unicode_identifier_and_crlf_are_preserved(self, tmp_path, jedi_required):
        source = tmp_path / "unicode.py"
        original = b"caf\xc3\xa9 = 1\r\nprint(caf\xc3\xa9)\r\n"
        source.write_bytes(original)
        store, result = preview(tmp_path, source, 1, 1, "naïve")
        assert source.read_bytes() == original
        assert "naïve = 1" in result.output
        assert "print(naïve)" in result.output
        plan_id = result.metadata["plan_id"]
        registry = shared_tool_registry("coding", tmp_path, rename_plans=store)
        apply_tool = registry.get("rename_apply")
        assert isinstance(apply_tool, RenameApplyTool)
        applied = apply_tool.run(
            ToolCall("rename_apply", {"plan_id": plan_id}), ToolContext(tmp_path)
        )
        assert not applied.is_error, applied.output
        updated = source.read_bytes()
        assert b"\r\n" in updated
        assert b"\n" not in updated.replace(b"\r\n", b"")

    def test_bad_identifier_cursor_syntax_and_unsupported_paths_refuse(
        self, tmp_path, jedi_required
    ):
        source = tmp_path / "good.py"
        source.write_text("value = 1\n", encoding="utf-8")
        tool = RenamePreviewTool(RenamePlanStore(tmp_path))
        context = ToolContext(tmp_path)

        def run(path, line, column, name):
            return tool.run(
                ToolCall(
                    "rename_preview",
                    {"path": path, "line": line, "column": column, "new_name": name},
                ),
                context,
            )

        assert run("good.py", 1, 1, "class").is_error
        assert run("good.py", 1, 20, "other").is_error
        assert run("../outside.py", 1, 1, "other").is_error
        assert run("good.txt", 1, 1, "other").is_error
        malformed = tmp_path / "broken.py"
        malformed.write_text("def broken(:\n", encoding="utf-8")
        assert run("broken.py", 1, 5, "fixed").is_error

    def test_symlink_paths_are_refused(self, tmp_path, jedi_required):
        source = tmp_path / "real.py"
        source.write_text("value = 1\n", encoding="utf-8")
        link = tmp_path / "linked.py"
        try:
            link.symlink_to(source)
        except (OSError, NotImplementedError):
            pytest.skip("symbolic links are not available for this user")
        _, result = preview(tmp_path, link, 1, 1, "other")
        assert result.is_error

    def test_stale_plan_is_consumed_without_mutating_files(self, tmp_path, jedi_required):
        source, caller = package_fixture(tmp_path)
        store, result = preview(tmp_path, source, 1, 7, "Gadget")
        caller.write_text(caller.read_text(encoding="utf-8") + "# concurrent edit\n")
        before_source = source.read_bytes()
        tool = RenameApplyTool(store)
        applied = tool.run(
            ToolCall("rename_apply", {"plan_id": result.metadata["plan_id"]}),
            ToolContext(tmp_path),
        )
        assert applied.is_error
        assert "stale" in applied.output
        assert source.read_bytes() == before_source

    def test_edit_during_jedi_analysis_refuses_preview(self, tmp_path, jedi_required, monkeypatch):
        from ai_agent.tools import refactor

        source, caller = package_fixture(tmp_path)
        original_rename = refactor._jedi_rename

        def rename_then_edit(*args, **kwargs):
            result = original_rename(*args, **kwargs)
            caller.write_text(
                caller.read_text(encoding="utf-8") + "# concurrent edit\n", encoding="utf-8"
            )
            return result

        monkeypatch.setattr(refactor, "_jedi_rename", rename_then_edit)
        tool = RenamePreviewTool(RenamePlanStore(tmp_path))
        result = tool.run(
            ToolCall(
                "rename_preview",
                {
                    "path": "sample_pkg/models.py",
                    "line": 1,
                    "column": 7,
                    "new_name": "Gadget",
                },
            ),
            ToolContext(tmp_path),
        )
        assert result.is_error
        assert "changed while Jedi was preparing preview" in result.output
        assert source.read_text(encoding="utf-8") == "class Widget:\n    pass\n"
        assert caller.read_text(encoding="utf-8").endswith("# concurrent edit\n")

    def test_interactive_approval_displays_full_immutable_diff(self, tmp_path, jedi_required):
        source, caller = package_fixture(tmp_path)
        store, result = preview(tmp_path, source, 1, 7, "Gadget")
        prompts = []
        permissions = PermissionManager(
            PermissionPolicy.interactive(),
            lambda call, category: prompts.append((call, category)) or True,
        )
        registry = scoped_registry(
            shared_tool_registry("coding", tmp_path, rename_plans=store),
            permissions,
            tmp_path,
            "test-task",
            "test-run",
        )
        apply_tool = registry.get("rename_apply")
        assert apply_tool is not None
        request = ToolCall("rename_apply", {"plan_id": result.metadata["plan_id"]})
        assert permissions.check_and_authorize(apply_tool, request)
        displayed, category = prompts[0]
        assert category is ToolCategory.WRITE
        assert displayed.arguments["plan_sha256"] == result.metadata["plan_sha256"]
        plan = store.get(result.metadata["plan_id"], ToolContext(tmp_path))
        assert plan is not None
        assert displayed.arguments["complete_diff"] == plan.diff
        assert len(json.dumps(displayed.arguments, ensure_ascii=True)) < 64_000
        assert "Widget" in source.read_text(encoding="utf-8")
        assert "Widget" in caller.read_text(encoding="utf-8")

    def test_denied_approval_does_not_apply_plan(self, tmp_path, jedi_required):
        source, caller = package_fixture(tmp_path)
        store, result = preview(tmp_path, source, 1, 7, "Gadget")
        registry = shared_tool_registry("coding", tmp_path, rename_plans=store)
        apply_tool = registry.get("rename_apply")
        assert isinstance(apply_tool, RenameApplyTool)
        permissions = PermissionManager(PermissionPolicy.interactive(), lambda _call, _cat: False)
        request = ToolCall("rename_apply", {"plan_id": result.metadata["plan_id"]})
        assert not permissions.check_and_authorize(apply_tool, request)
        assert source.read_text(encoding="utf-8") == "class Widget:\n    pass\n"
        assert "Widget" in caller.read_text(encoding="utf-8")

    def test_plan_expires_and_cannot_be_reused(self, tmp_path, jedi_required, monkeypatch):
        source, _ = package_fixture(tmp_path)
        store, result = preview(tmp_path, source, 1, 7, "Gadget")
        handle = result.metadata["plan_id"]
        plan = store._plans[handle]
        store._plans[handle] = replace(plan, expires_at=0)
        apply_tool = RenameApplyTool(store)
        request = ToolCall("rename_apply", {"plan_id": handle})
        assert apply_tool.approval_call(request) is None
        assert apply_tool.run(request, ToolContext(tmp_path)).is_error

        store, result = preview(tmp_path, source, 1, 7, "Gadget")
        apply_tool = RenameApplyTool(store)
        request = ToolCall("rename_apply", {"plan_id": result.metadata["plan_id"]})
        assert not apply_tool.run(request, ToolContext(tmp_path)).is_error
        assert apply_tool.run(request, ToolContext(tmp_path)).is_error

    def test_partial_atomic_apply_reports_prior_effects(self, tmp_path, jedi_required, monkeypatch):
        source, caller = package_fixture(tmp_path)
        store, result = preview(tmp_path, source, 1, 7, "Gadget")
        handle = result.metadata["plan_id"]
        plan = store.get(handle, ToolContext(tmp_path))
        assert plan is not None and len(plan.changes) == 2
        from ai_agent.tools import refactor

        original_replace = refactor._atomic_replace
        calls = 0

        def fail_second(change):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("fixture write error")
            original_replace(change)

        monkeypatch.setattr(refactor, "_atomic_replace", fail_second)
        apply_tool = RenameApplyTool(store)
        applied = apply_tool.run(
            ToolCall("rename_apply", {"plan_id": handle}), ToolContext(tmp_path)
        )
        assert applied.is_error
        assert "No automatic rollback" in applied.output
        assert len(applied.metadata["applied"]) == 1
        assert "Gadget" in caller.read_text(encoding="utf-8")
        assert "Widget" in source.read_text(encoding="utf-8")

    def test_missing_optional_dependency_is_explicit(self, tmp_path, monkeypatch):
        source = tmp_path / "missing.py"
        source.write_text("value = 1\n", encoding="utf-8")
        original = importlib.import_module

        def without_jedi(name, *args, **kwargs):
            if name == "jedi":
                raise ImportError("optional dependency absent")
            return original(name, *args, **kwargs)

        monkeypatch.setattr("ai_agent.tools.refactor.importlib.import_module", without_jedi)
        with pytest.raises(RuntimeError, match="optional extra"):
            _jedi_rename("value = 1\n", source, tmp_path, 1, 0, "other")

    def test_foreground_registries_share_only_owner_local_plan_state(self, tmp_path, jedi_required):
        from ai_provider.foreground_tools import ForegroundTools

        source, _ = package_fixture(tmp_path)
        owner = ForegroundTools(tmp_path)
        try:
            first = owner.registry()
            preview_tool = first.get("rename_preview")
            assert isinstance(preview_tool, RenamePreviewTool)
            first_store = preview_tool.plans
            result = preview_tool.run(
                ToolCall(
                    "rename_preview",
                    {
                        "path": "sample_pkg/models.py",
                        "line": 1,
                        "column": 7,
                        "new_name": "Gadget",
                    },
                ),
                ToolContext(tmp_path),
            )
            assert not result.is_error

            second = owner.registry()
            second_preview = second.get("rename_preview")
            apply_tool = second.get("rename_apply")
            assert isinstance(second_preview, RenamePreviewTool)
            assert isinstance(apply_tool, RenameApplyTool)
            assert second_preview.plans is first_store
            approval = apply_tool.approval_call(
                ToolCall("rename_apply", {"plan_id": result.metadata["plan_id"]})
            )
            assert approval is not None
            assert approval.arguments["complete_diff"] in result.output
        finally:
            owner.close()


def test_coding_profile_exposes_preview_and_apply_separately():
    assert "rename_preview" in CODING_PROFILE.tool_names
    assert "rename_apply" in CODING_PROFILE.tool_names


class TestPythonNavigate:
    def test_resolves_workspace_definition_and_references(self, tmp_path, jedi_required):
        source, caller = package_fixture(tmp_path)
        tool = PythonNavigateTool()
        context = ToolContext(tmp_path)

        definitions = tool.run(
            ToolCall(
                "python_navigate",
                {
                    "path": "sample_pkg/client.py",
                    "line": 3,
                    "column": 9,
                    "operation": "definitions",
                },
            ),
            context,
        )
        assert not definitions.is_error, definitions.output
        assert {(result["path"], result["line"]) for result in definitions.metadata["results"]} == {
            ("sample_pkg/models.py", 1)
        }

        references = tool.run(
            ToolCall(
                "python_navigate",
                {
                    "path": "sample_pkg/models.py",
                    "line": 1,
                    "column": 7,
                    "operation": "references",
                },
            ),
            context,
        )
        assert not references.is_error, references.output
        reference_locations = {
            (result["path"], result["line"]) for result in references.metadata["results"]
        }
        assert ("sample_pkg/models.py", 1) in reference_locations
        assert ("sample_pkg/client.py", 1) in reference_locations
        assert ("sample_pkg/client.py", 3) in reference_locations
        assert source.read_text(encoding="utf-8") == "class Widget:\n    pass\n"
        assert "Widget" in caller.read_text(encoding="utf-8")

    def test_refuses_invalid_path_cursor_and_operation(self, tmp_path, jedi_required):
        source = tmp_path / "source.py"
        source.write_text("value = 1\n", encoding="utf-8")
        tool = PythonNavigateTool()
        context = ToolContext(tmp_path)

        def run(path, line, column, operation="definitions"):
            return tool.run(
                ToolCall(
                    "python_navigate",
                    {"path": path, "line": line, "column": column, "operation": operation},
                ),
                context,
            )

        assert run("../outside.py", 1, 1).is_error
        assert run("source.py", 1, 20).is_error
        assert run("source.py", 1, 1, "rename").is_error
        assert run("source.py", 0, 1).is_error

    def test_bounds_results_and_excludes_paths_outside_workspace(self, tmp_path, monkeypatch):
        source = tmp_path / "source.py"
        source.write_text("value = 1\n" * 102, encoding="utf-8")
        outside = tmp_path.parent / "outside.py"
        names = [
            SimpleNamespace(
                module_path=source,
                line=line,
                column=0,
                name="value",
                description="name",
            )
            for line in range(1, 103)
        ]
        names.append(
            SimpleNamespace(
                module_path=outside,
                line=1,
                column=0,
                name="value",
                description="external",
            )
        )
        monkeypatch.setattr("ai_agent.tools.refactor._jedi_navigate", lambda *_args: names)

        result = PythonNavigateTool().run(
            ToolCall(
                "python_navigate",
                {"path": "source.py", "line": 1, "column": 1, "operation": "references"},
            ),
            ToolContext(tmp_path),
        )

        assert not result.is_error
        assert len(result.metadata["results"]) == 100
        assert result.metadata["truncated"] is True
        assert result.metadata["excluded_outside_workspace_or_invalid"] == 1
        assert all(item["path"] == "source.py" for item in result.metadata["results"])

    def test_navigation_is_available_in_native_and_shared_coding_profiles(self):
        assert "python_navigate" in CODING_PROFILE.tool_names
        assert isinstance(default_coding_tools().get("python_navigate"), PythonNavigateTool)
        assert isinstance(shared_tool_registry("coding").get("python_navigate"), PythonNavigateTool)
