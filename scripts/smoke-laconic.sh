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

# 1. Activation is opt-in: the shipped register declares `"default": "off"`, so a
# SessionStart with nothing configured must inject NOTHING and write no flag.
# Guards the data change end to end — `off` is not one of the register's level
# tokens, so loadOne has to accept it as a special rather than falling through to
# tokens[0], which would activate at whatever level is declared first.
optout="$(CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-activate.js")"
[ "$optout" = "OK" ] || fail "opt-in default leaked register text into SessionStart: [$optout]"
[ -e "$tmp/.laconic-active" ] && fail "opt-in default still wrote an active flag"

# 1b. With a level configured, SessionStart activates, writes the flag, emits the
# body. Also sets up the active flag checks 2-6 read.
out="$(CLAUDE_CONFIG_DIR="$tmp" LACONIC_DEFAULT_MODE=laconic node "$H/laconic-activate.js")"
grep -q "LACONIC REGISTER ACTIVE — level: laconic" <<<"$out" || fail "activate header missing"
[ "$(cat "$tmp/.laconic-active")" = "laconic" ] || fail "flag not written as 'laconic'"
grep -q "sharp colleague" <<<"$out" || fail "register body not emitted"
# only the active level's intensity row survives the filter
levels="$(grep -oE '\*\*laconic(-lite|-ultra)?\*\*' <<<"$out" | sort -u | tr '\n' ' ')"
[ "$levels" = "**laconic** " ] || fail "level filter leaked other rows: [$levels]"

# 2. UserPromptSubmit re-injects the per-turn reminder from the active register.
rein="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js")"
grep -q "LACONIC REGISTER ACTIVE (laconic)" <<<"$rein" || fail "per-turn reinforce missing"
# The reinforce string is the only copy of the register that survives compaction,
# so the safety carve-outs and the full boundary have to be in it, not only in
# register.md.
grep -q "security warnings" <<<"$rein" || fail "per-turn reinforce lost the Auto-Clarity carve-outs"
grep -q "no dropped articles" <<<"$rein" || fail "per-turn reinforce lost the full shipped-artifact boundary"

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

# 7. Bare `/laconic`, from the cleared state left by checks 5-6, activates. This
# is the path the README and the skill document, and the one the opt-in default
# would otherwise have broken: resolving a bare `/laconic` through the SESSION
# default would read 'off' and deactivate, so the documented activation command
# would have been a no-op. It resolves through getActivationLevel() instead.
printf '%s' '{"prompt":"/laconic"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$tmp/.laconic-active" 2>/dev/null)" = "laconic" ] || fail "bare /laconic did not activate at 'laconic'"
# and it really does re-inject once active
rein2="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js")"
grep -q "LACONIC REGISTER ACTIVE (laconic)" <<<"$rein2" || fail "no reinforcement after bare /laconic activation"

# 8. Bare hook install (no registers/ dir): the resolved default must still be
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

# 9. The level filter keys on DECLARED level tokens, not on "bullet whose first
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

echo "smoke-laconic: PASS (9 checks)"
