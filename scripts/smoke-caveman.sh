#!/usr/bin/env bash
# smoke-caveman.sh — runtime check that the PATCHED caveman per-turn hook
# actually EMITS the allocation reframe.
#
# Why this exists: render.py's patch step proves the anchor matched and the text
# was substituted. It does NOT prove the resulting hook still runs and injects.
# A future edit could be syntactically valid (node --check passes) yet throw at
# runtime — and the hook swallows its own errors (`catch (e) { /* Silent fail */ }`),
# so a broken injection would vanish with no trace. This drives the real hook
# with a real UserPromptSubmit payload and asserts the patched framing comes out.
#
# Run after scripts/build.sh. Requires node. Exits nonzero (loud) on any miss.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/plugins/caveman/src/hooks/caveman-mode-tracker.js"

[ -f "$HOOK" ] || { echo "smoke-caveman: hook not built: $HOOK (run build.sh first)" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "smoke-caveman: node not found on PATH" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf 'full' > "$tmp/.caveman-active"

# The hook reads the active-mode flag from $CLAUDE_CONFIG_DIR/.caveman-active and
# emits a UserPromptSubmit additionalContext block when a non-independent mode is
# active. Feed it an ordinary prompt (no /caveman command) so it takes the
# per-turn reinforcement path.
out="$(printf '%s' '{"prompt":"hello there"}' | CLAUDE_CONFIG_DIR="$tmp" node "$HOOK")"

# Sentinels: the unpatched line would contain none of the allocation framing.
fail=0
for needle in \
  "CAVEMAN MODE ACTIVE" \
  "FLOOR for low-value" \
  "never the reasoning" \
  "Err verbose"; do
  case "$out" in
    *"$needle"*) ;;
    *) echo "smoke-caveman: MISSING expected text: $needle" >&2; fail=1 ;;
  esac
done

if [ "$fail" -ne 0 ]; then
  echo "smoke-caveman: FAIL — per-turn hook did not emit the patched allocation framing" >&2
  echo "---- hook output ----" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi

echo "smoke-caveman: OK — per-turn hook emits the patched allocation framing"
