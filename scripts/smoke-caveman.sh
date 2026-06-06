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

# --- SessionStart hook: must load SKILL.md, be complete, and stay under cap ---
ACTIVATE="$REPO_ROOT/plugins/caveman/src/hooks/caveman-activate.js"
[ -f "$ACTIVATE" ] || { echo "smoke-caveman: activate hook not built: $ACTIVATE" >&2; exit 1; }
ss="$(CLAUDE_CONFIG_DIR="$tmp" node "$ACTIVATE")"

# The patched path (edit #5) must load SKILL.md, so the Allocation section AND
# the final Boundaries section must both appear: presence of the first proves it
# loaded the skill (not the hardcoded fallback); presence of the last proves the
# output was not cut off mid-content.
for needle in "## Allocation: terseness is a floor" "## Boundaries"; do
  case "$ss" in
    *"$needle"*) ;;
    *) echo "smoke-caveman: SessionStart MISSING expected text: $needle" >&2; fail=1 ;;
  esac
done

# Claude Code caps hook output at 10000 chars; past that the text degrades to a
# file-pointer and stops injecting inline (docs: code.claude.com/docs/en/hooks).
# Fail loud with margin so a future SKILL.md bloat is caught here, not discovered
# in production.
ss_len=$(printf '%s' "$ss" | wc -c | tr -d ' ')
if [ "$ss_len" -ge 9000 ]; then
  echo "smoke-caveman: SessionStart output ${ss_len}c >= 9000c safety margin (hard cap 10000c) — trim SKILL.md before it degrades to a file-pointer" >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "smoke-caveman: FAIL — patched hooks did not emit the expected framing (see above)" >&2
  exit 1
fi

echo "smoke-caveman: OK — per-turn (${#out}c) + SessionStart (${ss_len}c / 10000c cap) emit the patched framing"
