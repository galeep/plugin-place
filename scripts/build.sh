#!/usr/bin/env bash
# build.sh — regenerate plugins/ and .claude-plugin/marketplace.json from plugins.yaml
#
# Idempotent: blows away the plugins/sci-* directories for `built` plugins and
# rebuilds them by copying skill directories out of the pinned submodule.
# `vendored` plugins are not touched — they live as submodules and we just
# point marketplace.json at them.
#
# Requirements: python3 with PyYAML.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

[[ -f "$REPO_ROOT/plugins.yaml" ]] || { echo "plugins.yaml not found" >&2; exit 1; }

# Verify both submodules are present and have content.
for sub in vendor/scientific-agent-skills vendor/claude-scientific-writer; do
  [[ -d "$sub/.git" || -f "$sub/.git" ]] || {
    echo "submodule missing or uninitialised: $sub" >&2
    echo "run: git submodule update --init --recursive" >&2
    exit 1
  }
done

mkdir -p plugins .claude-plugin
python3 "$REPO_ROOT/scripts/render.py"
echo "build.sh: done"
