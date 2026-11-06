"""Duplication scanner: rename-clones group, the rest does not."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/find-duplication.py"
SPEC = importlib.util.spec_from_file_location("find_duplication", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


def test_rename_clone_groups(tmp_path) -> None:
    first = tmp_path / "a.py"
    first.write_text(
        "def load_key(path):\n"
        "    text = path.read_text(encoding='utf-8')\n"
        "    values = [line.strip() for line in text.splitlines() if line]\n"
        "    if len(values) != 1:\n"
        "        raise ValueError('need one')\n"
        "    return values[0]\n",
        encoding="utf-8",
    )
    second = tmp_path / "b.py"
    second.write_text(
        "def fetch_secret(store):\n"
        "    data = store.read_text(encoding='utf-8')\n"
        "    items = [row.strip() for row in data.splitlines() if row]\n"
        "    if len(items) != 1:\n"
        "        raise ValueError('need one')\n"
        "    return items[0]\n",
        encoding="utf-8",
    )
    records = scanner.scan_file(first) + scanner.scan_file(second)
    groups = scanner.find_groups(records, min_nodes=10, min_lines=5)
    assert len(groups) == 1
    assert {item["path"] for item in groups[0]} == {str(first), str(second)}


def test_different_logic_not_grouped(tmp_path) -> None:
    first = tmp_path / "a.py"
    first.write_text(
        "def total(values):\n"
        "    result = 0\n"
        "    for value in values:\n"
        "        result = result + value\n"
        "    return result\n",
        encoding="utf-8",
    )
    second = tmp_path / "b.py"
    second.write_text(
        "def joined(values):\n"
        "    parts = []\n"
        "    for value in values:\n"
        "        parts.append(str(value))\n"
        '    return ",".join(parts)\n',
        encoding="utf-8",
    )
    records = scanner.scan_file(first) + scanner.scan_file(second)
    assert scanner.find_groups(records, min_nodes=10, min_lines=5) == []


def test_tiny_matches_below_threshold_ignored(tmp_path) -> None:
    first = tmp_path / "a.py"
    first.write_text("def one():\n    return 1\n", encoding="utf-8")
    second = tmp_path / "b.py"
    second.write_text("def two():\n    return 2\n", encoding="utf-8")
    records = scanner.scan_file(first) + scanner.scan_file(second)
    assert scanner.find_groups(records, min_nodes=30, min_lines=8) == []


def test_json_output_parseable(tmp_path, capsys) -> None:
    first = tmp_path / "a.py"
    first.write_text(
        "def load_key(path):\n"
        "    text = path.read_text(encoding='utf-8')\n"
        "    values = [line.strip() for line in text.splitlines() if line]\n"
        "    if len(values) != 1:\n"
        "        raise ValueError('need one')\n"
        "    return values[0]\n",
        encoding="utf-8",
    )
    out = tmp_path / "groups.json"
    assert (
        scanner.main([str(tmp_path), "--min-nodes", "10", "--min-lines", "5", "--json", str(out)])
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert "clone groups" in capsys.readouterr().out


def test_unparseable_file_warns_exit_zero(tmp_path, capsys) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n", encoding="utf-8")
    assert scanner.scan_file(bad) == []
    assert "skipping" in capsys.readouterr().err
    assert scanner.main([str(tmp_path)]) == 0
