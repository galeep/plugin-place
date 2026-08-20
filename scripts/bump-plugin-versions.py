#!/usr/bin/env python3
"""Entry point for the pull-request version bump. Logic lives in the library.

    python3 scripts/bump-plugin-versions.py --base-ref origin/main --apply
    python3 scripts/bump-plugin-versions.py --base-ref origin/main --check

Run as a script, so sys.path[0] is scripts/ and `from scripts.lib import ...`
would fail. Add the repo root the same way scripts/render.py does.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.lib import plugin_versions  # noqa: E402

if __name__ == "__main__":
    sys.exit(plugin_versions.main(sys.argv[1:]))
