import importlib

def test_lib_package_imports():
    mod = importlib.import_module("scripts.lib")
    assert mod is not None


def test_every_upstream_has_a_current_license_fingerprint():
    """plugins.yaml must record the licensing terms actually present at each pin.

    Guards the tripwire itself: if this drifts, an upstream relicensed and
    nobody acknowledged it. Re-record with scripts/license-fingerprint.py --write
    AFTER reading what changed.
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    out = subprocess.run(
        [sys.executable, "scripts/license-fingerprint.py", "--check", "--strict"],
        cwd=repo_root, text=True, capture_output=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_skill_owner_index_reports_real_cross_plugin_overlap():
    """Overlap is expected here, so this pins the reporter, not a uniqueness rule.

    The writer bundle deliberately re-ships skills that also live in focused
    sci-*/kdense-* plugins, and its description tells users to install one or the
    other. A gate would fail on ~20 intentional cases; what was missing was
    NAMING a newly-overlapping skill instead of letting it land as an anonymous
    "+N skills" line in a sync diff.
    """
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "render_mod", repo_root / "scripts" / "render.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    index = mod.skill_owner_index()
    assert index, "no skills found — was the tree built?"
    # Every value is a sorted, deduplicated plugin list.
    for skill, plugins in index.items():
        assert plugins == sorted(set(plugins)), skill
    # docx has a designated home; whoever else ships it must be visible here.
    assert "kdense-document-skills" in index.get("docx", []), index.get("docx")
    # The overlap the writer bundle creates on purpose must be represented.
    assert any(len(v) > 1 for v in index.values())
