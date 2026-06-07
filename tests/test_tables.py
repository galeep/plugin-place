import pytest
from scripts.lib import tables

def test_gate_passes_when_complete():
    table = {"a": "plug-x", "b": "plug-y"}
    tables.coverage_gate({"a", "b"}, table, {"plug-x", "plug-y"}, "skill")
    # no exception == pass

def test_gate_fails_on_missing_item():
    table = {"a": "plug-x"}
    with pytest.raises(SystemExit) as e:
        tables.coverage_gate({"a", "b"}, table, {"plug-x"}, "skill")
    assert "b" in str(e.value)

def test_gate_fails_on_unassigned():
    table = {"a": "UNASSIGNED"}
    with pytest.raises(SystemExit) as e:
        tables.coverage_gate({"a"}, table, {"plug-x"}, "agent")
    assert "UNASSIGNED" in str(e.value)

def test_gate_fails_on_unknown_plugin():
    table = {"a": "ghost-plugin"}
    with pytest.raises(SystemExit) as e:
        tables.coverage_gate({"a"}, table, {"plug-x"}, "skill")
    assert "ghost-plugin" in str(e.value)

def test_gate_fails_on_stale_entry():
    table = {"a": "plug-x", "gone": "plug-x"}
    with pytest.raises(SystemExit) as e:
        tables.coverage_gate({"a"}, table, {"plug-x"}, "skill")
    assert "gone" in str(e.value) and "stale" in str(e.value)

def test_members_for_plugin():
    table = {"a": "plug-x", "b": "plug-y", "c": "plug-x"}
    assert tables.members_for(table, "plug-x") == ["a", "c"]
