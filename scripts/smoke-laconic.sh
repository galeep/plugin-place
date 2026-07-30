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

# 7. Bare hook install (no registers/ dir): the resolved default must still be
# on the whitelist. Checks 1-6 all run with registers/ present, so this path was
# uncovered — and it is where the failure hid: registryDefault() returns
# FALLBACK_DEFAULT unconditionally, so if VALID_MODES is built from an empty
# registry alone it collapses to ['off'], the hooks write a flag readFlag() then
# refuses, and activation silently no-ops. Layout mirrors the real one
# (hooks at <root>/src/hooks, registers at <root>/registers) with registers/ absent.
bare="$tmp/bare/src/hooks"
mkdir -p "$bare"
cp "$H"/laconic-config.js "$H"/laconic-registry.js "$bare/"
[ -e "$tmp/bare/registers" ] && fail "bare fixture must not have a registers/ dir"
node -e '
  const cfg = require(process.argv[1]);
  const def = cfg.getDefaultMode();
  if (!cfg.VALID_MODES.includes(def)) {
    console.error("default mode " + JSON.stringify(def) + " not in VALID_MODES " + JSON.stringify(cfg.VALID_MODES));
    process.exit(1);
  }
' "$bare/laconic-config.js" || fail "bare install: resolved default not accepted by its own whitelist"

# and the flag round-trips: what the hooks write, readFlag must accept back.
node -e '
  const cfg = require(process.argv[1]);
  const p = process.argv[2] + "/.laconic-active";
  cfg.safeWriteFlag(p, cfg.getDefaultMode());
  const got = cfg.readFlag(p);
  if (got !== cfg.getDefaultMode()) {
    console.error("round-trip lost the flag: wrote " + cfg.getDefaultMode() + ", read " + JSON.stringify(got));
    process.exit(1);
  }
' "$bare/laconic-config.js" "$tmp" || fail "bare install: flag write/read round-trip broken"

# 8. The level filter keys on DECLARED level tokens, not on "bullet whose first
# word ends in a colon". Regression guard: `- **Keep**: logic connectives
# (because, so, but, unless, therefore)` in register.md matches that shape, so it
# used to be filtered out as another level's example line at EVERY level — the
# register shipped its "Drop" rule with the "Keep" guardrail silently missing,
# and at laconic-lite/laconic-ultra the phrase "logic connectives" vanished from
# the injected body entirely. Driven against the real register.md at all three
# levels: the Keep rule must survive, and exactly the active level's example
# lines must survive.
for lvl in laconic-lite laconic laconic-ultra; do
  ftmp="$tmp/filter-$lvl"; mkdir -p "$ftmp"
  fout="$(CLAUDE_CONFIG_DIR="$ftmp" LACONIC_DEFAULT_MODE="$lvl" node "$H/laconic-activate.js")"
  grep -q "logic connectives" <<<"$fout" || fail "level filter dropped the 'logic connectives' Keep rule at $lvl"
  grep -q '^- \*\*Keep\*\*: logic connectives' <<<"$fout" || fail "level filter ate the '- **Keep**:' prose bullet at $lvl"
  ex="$(grep -oE '^- laconic(-lite|-ultra)?:' <<<"$fout" | sort -u | tr -d '\n')"
  [ "$ex" = "- $lvl:" ] || fail "example lines at $lvl should be only '- $lvl:', got [$ex]"
done

echo "smoke-laconic: PASS (8 checks)"
