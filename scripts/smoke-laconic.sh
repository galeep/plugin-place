#!/usr/bin/env bash
# smoke-laconic.sh — runtime gate for the laconic register plugin.
#
# node --check proves the hooks parse; it does NOT prove they run and emit the
# right thing. The hooks swallow their own errors (silent-fail by design), so a
# runtime throw would vanish with no trace. This drives the real hooks with real
# hook payloads against a temp CLAUDE_CONFIG_DIR and asserts the observable
# behavior. Deterministic, no network, no LLM. Exits nonzero (loud) on any miss.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
H="$REPO_ROOT/plugins/laconic/src/hooks"
command -v node >/dev/null 2>&1 || { echo "smoke-laconic: node not found on PATH" >&2; exit 1; }
for f in laconic-activate.js laconic-mode-tracker.js laconic-config.js laconic-registry.js; do
  [ -f "$H/$f" ] || { echo "smoke-laconic: missing hook $H/$f" >&2; exit 1; }
done

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
fail() { echo "smoke-laconic: FAIL — $1" >&2; exit 1; }

# 1. SessionStart activates at the default level, writes the flag, emits the body.
out="$(CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-activate.js")"
grep -q "LACONIC REGISTER ACTIVE — level: laconic" <<<"$out" || fail "activate header missing"
[ "$(cat "$tmp/.laconic-active")" = "laconic" ] || fail "flag not written as 'laconic'"
grep -q "sharp colleague" <<<"$out" || fail "register body not emitted"
# only the active level's intensity row survives the filter
levels="$(grep -oE '\*\*laconic(-lite|-ultra)?\*\*' <<<"$out" | sort -u | tr '\n' ' ')"
[ "$levels" = "**laconic** " ] || fail "level filter leaked other rows: [$levels]"

# 2. UserPromptSubmit re-injects the per-turn reminder from the active register.
rein="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js")"
grep -q "LACONIC REGISTER ACTIVE (laconic)" <<<"$rein" || fail "per-turn reinforce missing"

# 3. /laconic <level> switches the flag.
printf '%s' '{"prompt":"/laconic laconic-ultra"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$tmp/.laconic-active")" = "laconic-ultra" ] || fail "/laconic laconic-ultra did not switch level"

# 4. An unknown level is ignored (no silent overwrite).
printf '%s' '{"prompt":"/laconic bogus"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$tmp/.laconic-active")" = "laconic-ultra" ] || fail "unknown level clobbered the flag"

# 5. Deactivation clears the flag.
printf '%s' '{"prompt":"stop laconic"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js" >/dev/null
[ -f "$tmp/.laconic-active" ] && fail "flag not cleared on 'stop laconic'"

# 6. A cleared flag emits no per-turn reminder (no stray injection).
empty="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js")"
[ -z "$empty" ] || fail "reminder emitted while register inactive"

echo "smoke-laconic: PASS (6 checks)"
