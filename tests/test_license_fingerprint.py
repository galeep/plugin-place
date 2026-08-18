"""Tests for scripts/license-fingerprint.py.

The duplicate-key bug these cover shipped because the original eleven tests
exercised only the pure hashing helpers and never `write_fingerprints`. The
writer is the half that MUTATES plugins.yaml and the half the nightly runs
unattended, so it is the half that needed the tests.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script():
    """Import the hyphenated script by path (not a valid module name)."""
    spec = importlib.util.spec_from_file_location(
        "license_fingerprint", REPO_ROOT / "scripts" / "license-fingerprint.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SAMPLE = """\
upstreams:
  alpha:
    submodule: vendor/alpha
    upstream_repo: acme/alpha
    license: MIT
  beta:
    submodule: vendor/beta
    upstream_repo: acme/beta
    license: MIT
    license_fingerprint: {old}
    # a trailing comment that must survive
    author: "Someone"

plugins:
  - name: x
"""


def rows_for(alpha, beta):
    # (name, recorded, actual, docs)
    return [
        ("alpha", None, alpha, ["LICENSE"]),
        ("beta", "b" * 64, beta, ["LICENSE"]),
    ]


def test_write_inserts_when_absent_and_replaces_when_present(tmp_path, monkeypatch):
    mod = load_script()
    p = tmp_path / "plugins.yaml"
    p.write_text(SAMPLE.format(old="b" * 64))
    monkeypatch.setattr(mod, "PLUGINS_YAML", p)

    mod.write_fingerprints(rows_for("1" * 64, "2" * 64))
    text = p.read_text()
    assert text.count("license_fingerprint:") == 2
    assert f"license_fingerprint: {'1' * 64}" in text
    assert f"license_fingerprint: {'2' * 64}" in text
    # Formatting and comments must survive a line-walking rewrite.
    assert "# a trailing comment that must survive" in text
    assert 'author: "Someone"' in text


def test_write_is_idempotent_and_does_not_duplicate_keys(tmp_path, monkeypatch):
    """The regression that would have corrupted plugins.yaml on the first nightly.

    `license:` sits above `license_fingerprint:`, so a one-pass writer reaching
    `license:` cannot yet know a fingerprint line follows. The original guessed
    "absent", inserted, then rewrote the real line lower down — one key became
    two on EVERY run (4 -> 8 -> 12 -> 16). yaml.safe_load takes duplicate keys
    silently with last-wins, so nothing downstream complained.
    """
    mod = load_script()
    p = tmp_path / "plugins.yaml"
    p.write_text(SAMPLE.format(old="b" * 64))
    monkeypatch.setattr(mod, "PLUGINS_YAML", p)

    for _ in range(5):
        mod.write_fingerprints(rows_for("1" * 64, "2" * 64))
        assert p.read_text().count("license_fingerprint:") == 2

    # Second identical write reports "no change" — the unreachable branch before.
    assert mod.write_fingerprints(rows_for("1" * 64, "2" * 64)) == 0


def test_write_refuses_when_a_submodule_is_not_checked_out(tmp_path, monkeypatch):
    mod = load_script()
    p = tmp_path / "plugins.yaml"
    p.write_text(SAMPLE.format(old="b" * 64))
    monkeypatch.setattr(mod, "PLUGINS_YAML", p)

    before = p.read_text()
    with pytest.raises(SystemExit) as e:
        mod.write_fingerprints(rows_for(None, "2" * 64))  # alpha unreadable
    assert "not checked out" in str(e.value)
    assert p.read_text() == before, "must not partially write"


def test_unreadable_is_reported_but_is_not_drift():
    """Recording an unverifiable upstream is the permanent-disarm path.

    If unreadable counted as drift, the documented remedy (`--write`) would
    record the empty-tree hash and silence the tripwire for good.
    """
    mod = load_script()
    rows = [("alpha", "a" * 64, None, None)]
    assert mod.drifted(rows) == []
    assert mod.unreadable(rows) == rows
    assert "Not verified" in mod.report(rows)


def test_drifted_actually_detects_a_changed_fingerprint():
    """Guards the guard.

    tests/test_smoke.py asserts `--check --strict` exits 0, which a drifted()
    that always returned [] would also satisfy — it cannot tell a working
    tripwire from a no-op one. This pins the positive direction.
    """
    mod = load_script()
    assert mod.drifted([("a", "a" * 64, "a" * 64, ["LICENSE"])]) == []
    assert len(mod.drifted([("a", "a" * 64, "c" * 64, ["LICENSE"])])) == 1
    # An upstream never fingerprinted has never been reviewed: that is drift.
    assert len(mod.drifted([("a", None, "c" * 64, ["LICENSE"])])) == 1
    assert "changed upstream" in mod.report([("a", "a" * 64, "c" * 64, ["LICENSE"])])


def test_report_survives_a_malformed_recorded_value():
    """A hand-typed int must not crash the advisory path."""
    mod = load_script()
    out = mod.report([("a", 12345, "c" * 64, ["LICENSE"])])
    assert "12345" in out
