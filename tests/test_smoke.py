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
