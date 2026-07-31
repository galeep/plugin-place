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

# Hermetic environment, set once for every check below. laconic-config.js resolves
# a mode from LACONIC_DEFAULT_MODE first and from
# $XDG_CONFIG_HOME/laconic/config.json (or ~/.config/laconic/config.json) second,
# both ahead of register data. Both outrank what these checks assert, and README.md
# tells users to set them, so inheriting a developer's real settings made this
# script fail on precisely the machines where the plugin is in daily use:
# `LACONIC_DEFAULT_MODE=laconic bash scripts/smoke-laconic.sh` failed check 1.
# Checks that need a default set it explicitly on their own invocation.
unset LACONIC_DEFAULT_MODE
export XDG_CONFIG_HOME="$tmp/xdg-empty"
mkdir -p "$XDG_CONFIG_HOME"

# 1. Activation is opt-in: the shipped register declares `"default": "off"`, so a
# SessionStart with nothing configured must inject NOTHING and write no flag.
# Guards the data change end to end — `off` is not one of the register's level
# tokens, so loadOne has to accept it as a special rather than falling through to
# tokens[0], which would activate at whatever level is declared first.
# SessionStart stdout becomes session context, so "injects nothing" has to mean
# literally nothing, not a placeholder token.
optout="$(CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-activate.js")"
[ -z "$optout" ] || fail "opt-in default wrote to SessionStart context: [$optout]"
[ -e "$tmp/.laconic-active" ] && fail "opt-in default still wrote an active flag"

# 1b. With a level configured, SessionStart activates, writes the flag, emits the
# body. Also sets up the active flag checks 2-6 read.
out="$(CLAUDE_CONFIG_DIR="$tmp" LACONIC_DEFAULT_MODE=laconic node "$H/laconic-activate.js")"
grep -q "LACONIC REGISTER ACTIVE — level: laconic" <<<"$out" || fail "activate header missing"
[ "$(cat "$tmp/.laconic-active")" = "laconic" ] || fail "flag not written as 'laconic'"
grep -q "sharp colleague" <<<"$out" || fail "register body not emitted"
# Only the active level's intensity row survives the filter. Anchored at ^| so it
# reads TABLE ROWS and nothing else: an unanchored `**laconic**` also matches the
# register's own prose, which made this assertion pass no matter what the row
# filter did.
rows="$(grep -oE '^\| \*\*laconic(-lite|-ultra)?\*\*' <<<"$out" | sort -u | tr '\n' ' ')"
[ "$rows" = "| **laconic** " ] || fail "level filter leaked other intensity rows: [$rows]"

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

# 5. Deactivation RECORDS itself, by prose and by the documented `/laconic off`
# (separate arms in the hook: the prose form goes through the wantsOff regex, the
# command form through the arg comparison, and only the first had a check). The flag
# is written rather than deleted, because absence means "no choice yet" and a
# configured default would otherwise turn the register back on at the next
# compaction.
printf '%s' '{"prompt":"stop laconic"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$tmp/.laconic-active" 2>/dev/null)" = "off" ] || fail "'stop laconic' did not record an off"
printf '%s' '{"prompt":"/laconic laconic-ultra"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js" >/dev/null
printf '%s' '{"prompt":"/laconic off"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$tmp/.laconic-active" 2>/dev/null)" = "off" ] || fail "'/laconic off' did not record an off"

# 6. A recorded off emits no per-turn reminder (no stray injection).
empty="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$tmp" node "$H/laconic-mode-tracker.js")"
[ -z "$empty" ] || fail "reminder emitted while register inactive"

# 7. Bare `/laconic`, from the recorded-off state left by checks 5-6, activates. This
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
# on the whitelist. Every check above runs with registers/ present, so this path
# was uncovered — and it is where the failure hid: registryDefault() returns
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
# Writes under $tmp/bare, not $tmp: $tmp/.laconic-active is the flag checks 1b-7
# share, and stamping the bare fixture's default onto it would hand any later
# check the wrong state.
node -e '
  const cfg = require(process.argv[1]);
  const p = process.argv[2] + "/.laconic-active";
  cfg.safeWriteFlag(p, cfg.getDefaultMode());
  const got = cfg.readFlag(p);
  if (got !== cfg.getDefaultMode()) {
    console.error("round-trip lost the flag: wrote " + cfg.getDefaultMode() + ", read " + JSON.stringify(got));
    process.exit(1);
  }
' "$bare/laconic-config.js" "$tmp/bare" || fail "bare install: flag write/read round-trip broken"

# and an argument-less activation on that same bare install resolves to a real
# level, never to a special. getActivationLevel()'s no-registry arm is the one
# that decides this, and returning 'off' there would make the documented
# activation command deactivate.
LACONIC_DEFAULT_MODE=off node -e '
  const cfg = require(process.argv[1]);
  const act = cfg.getActivationLevel();
  if (act === "off" || !cfg.VALID_MODES.includes(act)) {
    console.error("bare install activation level " + JSON.stringify(act) + " not a usable level; VALID_MODES " + JSON.stringify(cfg.VALID_MODES));
    process.exit(1);
  }
' "$bare/laconic-config.js" || fail "bare install: argument-less activation does not resolve to a level"
# and a configured level still outranks register data on the same install.
LACONIC_DEFAULT_MODE=laconic node -e '
  const cfg = require(process.argv[1]);
  if (cfg.getActivationLevel() !== "laconic" || cfg.getDefaultMode() !== "laconic") {
    console.error("configured level lost: default=" + cfg.getDefaultMode() + " activation=" + cfg.getActivationLevel());
    process.exit(1);
  }
' "$bare/laconic-config.js" || fail "bare install: LACONIC_DEFAULT_MODE did not win"

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

# 10. An activated level survives a later SessionStart. SessionStart fires on
# resume, clear and compact as well as startup (plugin.json sets no matcher), and
# the shipped register's default is 'off', so a hook that treated that as "be off"
# deleted the flag at the first compaction — taking the per-turn reinforcement
# with it, which is the one copy of the register that outlives a compaction. An
# 'off' from register DATA must therefore honor a level already on the flag, while
# an 'off' the user asked for explicitly (env or config) still clears it.
stmp="$tmp/sticky"; mkdir -p "$stmp"
printf '%s' '{"prompt":"/laconic laconic-ultra"}' | CLAUDE_CONFIG_DIR="$stmp" node "$H/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$stmp/.laconic-active" 2>/dev/null)" = "laconic-ultra" ] || fail "setup for check 10: /laconic laconic-ultra did not activate"
sout="$(CLAUDE_CONFIG_DIR="$stmp" node "$H/laconic-activate.js")"
[ "$(cat "$stmp/.laconic-active" 2>/dev/null)" = "laconic-ultra" ] || fail "SessionStart deleted an active flag under the opt-in default"
grep -q "REGISTER ACTIVE — level: laconic-ultra" <<<"$sout" || fail "SessionStart did not re-inject the held level: [$(head -1 <<<"$sout")]"
srein="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$stmp" node "$H/laconic-mode-tracker.js")"
grep -q "LACONIC REGISTER ACTIVE (laconic-ultra)" <<<"$srein" || fail "reinforcement stopped after a SessionStart"
# an explicit off still wins, and clears
koff="$(CLAUDE_CONFIG_DIR="$stmp" LACONIC_DEFAULT_MODE=off node "$H/laconic-activate.js")"
[ -z "$koff" ] || fail "explicit LACONIC_DEFAULT_MODE=off emitted text: [$koff]"
[ "$(cat "$stmp/.laconic-active" 2>/dev/null)" = "off" ] || fail "explicit LACONIC_DEFAULT_MODE=off left a level on the flag"

# 11. The register's alias resolves. `"aliases": { "notebook": "laconic" }` is
# data no check read, so an alias silently dropped from VALID_MODES would make the
# flag write get refused and activation no-op with nothing to show for it.
atmp="$tmp/alias"; mkdir -p "$atmp"
printf '%s' '{"prompt":"/laconic notebook"}' | CLAUDE_CONFIG_DIR="$atmp" node "$H/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$atmp/.laconic-active" 2>/dev/null)" = "notebook" ] || fail "alias '/laconic notebook' did not set the flag"
arein="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$atmp" node "$H/laconic-mode-tracker.js")"
grep -q "LACONIC REGISTER ACTIVE (laconic)" <<<"$arein" || fail "alias did not resolve to its canonical token in the reinforcement"

# 12. A registers/ dir that exists but holds only invalid registers must NOT
# activate. Every register rejected is a defect in the data, and the opt-in
# guarantee has to survive it: resolving to the hardcoded fallback there would
# activate at a level no register defines and emit the stub anchor, so a one-
# character JSON typo would read as a working install.
brk="$tmp/broken"; mkdir -p "$brk/src/hooks" "$brk/registers/laconic"
cp "$H"/laconic-*.js "$brk/src/hooks/"
printf '%s' '{ "id": "laconic", broken' > "$brk/registers/laconic/register.json"
printf '%s' 'body' > "$brk/registers/laconic/register.md"
btmp="$tmp/broken-cfg"; mkdir -p "$btmp"
bout="$(CLAUDE_CONFIG_DIR="$btmp" node "$brk/src/hooks/laconic-activate.js")"
[ -z "$bout" ] || fail "an all-invalid registers/ dir still injected text: [$bout]"
[ -e "$btmp/.laconic-active" ] && fail "an all-invalid registers/ dir still wrote an active flag"
# and the refusal is not one command deep: /laconic must not talk itself into the
# generic anchor by resolving to a level no register defines.
printf '%s' '{"prompt":"/laconic"}' | CLAUDE_CONFIG_DIR="$btmp" node "$brk/src/hooks/laconic-mode-tracker.js" >/dev/null
[ -e "$btmp/.laconic-active" ] && fail "/laconic activated a level on an install with no loadable register"
bout2="$(CLAUDE_CONFIG_DIR="$btmp" node "$brk/src/hooks/laconic-activate.js")"
[ -z "$bout2" ] || fail "defective install injected the generic anchor after a /laconic: [$bout2]"
# and it says so under LACONIC_DEBUG, because 'OK' alone is also what a healthy
# opt-in install prints: without a diagnostic the two are indistinguishable.
LACONIC_DEBUG=1 CLAUDE_CONFIG_DIR="$btmp" node "$brk/src/hooks/laconic-activate.js" 2>"$tmp/dbg.err" >/dev/null
grep -qE "skipped invalid register|no register in it loaded" "$tmp/dbg.err" || fail "LACONIC_DEBUG=1 said nothing about a registers/ dir with no usable register"

# 13. activationToken is pinned by a register that is NOT named after its own
# level tokens. Against the shipped register the field is untestable — its id
# `laconic` equals FALLBACK_DEFAULT, so deleting the field entirely still yields
# the same answer and the suite stays green.
alt="$tmp/alt"; mkdir -p "$alt/src/hooks" "$alt/registers/voice"
cp "$H"/laconic-*.js "$alt/src/hooks/"
printf '%s' '{"id":"voice","default":"off","statusline":"VOICE","tokens":{"voice-lite":"a","voice":"b"},"reinforce":"VOICE ACTIVE ({token})."}' > "$alt/registers/voice/register.json"
printf '%s' 'voice body' > "$alt/registers/voice/register.md"
vtmp="$tmp/alt-cfg"; mkdir -p "$vtmp"
printf '%s' '{"prompt":"/laconic"}' | CLAUDE_CONFIG_DIR="$vtmp" node "$alt/src/hooks/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$vtmp/.laconic-active" 2>/dev/null)" = "voice" ] || fail "bare /laconic on an opt-in register did not resolve to its eponymous token: [$(cat "$vtmp/.laconic-active" 2>/dev/null || echo none)]"
vrein="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$vtmp" node "$alt/src/hooks/laconic-mode-tracker.js")"
grep -q "VOICE ACTIVE (voice)" <<<"$vrein" || fail "activated register emitted no reinforcement of its own"

# 14. The command file's contract. validate-plugin.sh counts files in commands/
# and parses nothing, so nothing else checks that every level `argument-hint`
# advertises is a level the hooks accept, or that its link to the register
# resolves — the exact break commit 4 fixed by hand in SKILL.md.
cmd="$REPO_ROOT/plugins/laconic/commands/laconic.md"
[ -f "$cmd" ] || fail "commands/laconic.md missing"
# Tolerant of the ways YAML spells the same value: quoted or bare, bracketed or
# not. A stricter parser fails the gate on a valid rewrite instead of checking it.
hint="$(sed -n 's/^argument-hint: *//p' "$cmd" | head -1 | tr -d '"'"'"'[]')"
[ -n "$hint" ] || fail "commands/laconic.md has no parseable argument-hint"
node -e '
  const cfg = require(process.argv[1]);
  const bad = process.argv[2].split("|").filter(t => !cfg.VALID_MODES.includes(t));
  if (bad.length) {
    console.error("argument-hint advertises modes the hooks reject: " + JSON.stringify(bad) + "; VALID_MODES " + JSON.stringify(cfg.VALID_MODES));
    process.exit(1);
  }
' "$H/laconic-config.js" "$hint" || fail "commands/laconic.md argument-hint disagrees with VALID_MODES"
grep -oE '\(\.\./[^)]+\)' "$cmd" | tr -d '()' | while read -r rel; do
  [ -e "$REPO_ROOT/plugins/laconic/commands/$rel" ] || fail "commands/laconic.md links '$rel', which does not resolve"
done

# 15. A CONFIGURED level is a default, not a standing order. The flag holds the
# user's actual choice, so a level in env or config seeds a session that has none
# and must not overwrite one. Without this, `{"defaultMode":"laconic-lite"}` plus
# `/laconic laconic-ultra` reverted to laconic-lite at the next compaction: the same
# clobber as the opt-in bug, on the path the first fix did not cover.
ctmp="$tmp/configured"; mkdir -p "$ctmp/xdg/laconic"
printf '%s' '{"defaultMode":"laconic-lite"}' > "$ctmp/xdg/laconic/config.json"
cout="$(CLAUDE_CONFIG_DIR="$ctmp" XDG_CONFIG_HOME="$ctmp/xdg" node "$H/laconic-activate.js")"
[ "$(cat "$ctmp/.laconic-active" 2>/dev/null)" = "laconic-lite" ] || fail "configured level did not seed a fresh session"
grep -q "level: laconic-lite" <<<"$cout" || fail "configured level not injected on a fresh session"
printf '%s' '{"prompt":"/laconic laconic-ultra"}' | CLAUDE_CONFIG_DIR="$ctmp" XDG_CONFIG_HOME="$ctmp/xdg" node "$H/laconic-mode-tracker.js" >/dev/null
cout2="$(CLAUDE_CONFIG_DIR="$ctmp" XDG_CONFIG_HOME="$ctmp/xdg" node "$H/laconic-activate.js")"
[ "$(cat "$ctmp/.laconic-active" 2>/dev/null)" = "laconic-ultra" ] || fail "SessionStart reverted a switched level to the configured default"
grep -q "level: laconic-ultra" <<<"$cout2" || fail "SessionStart injected the configured level over the switched one"
# and an explicit off in the same config still wins over the flag (kill switch)
printf '%s' '{"defaultMode":"off"}' > "$ctmp/xdg/laconic/config.json"
CLAUDE_CONFIG_DIR="$ctmp" XDG_CONFIG_HOME="$ctmp/xdg" node "$H/laconic-activate.js" >/dev/null
[ "$(cat "$ctmp/.laconic-active" 2>/dev/null)" = "off" ] || fail "configured 'off' did not override an active level"

# 16. A flag that is PRESENT but unreadable is not this hook's to delete. Oversized,
# a symlink, or naming a token no register declares any more: all three read as null,
# and deleting on null cost the user their level whenever register.json was briefly
# unparseable mid-edit.
for bad in oversized unknown-token; do
  ftmp="$tmp/badflag-$bad"; mkdir -p "$ftmp"
  case "$bad" in
    oversized) head -c 200 /dev/zero | tr '\0' 'x' > "$ftmp/.laconic-active" ;;
    unknown-token) printf '%s' 'level-that-no-register-declares' > "$ftmp/.laconic-active" ;;
  esac
  before="$(cat "$ftmp/.laconic-active")"
  bout3="$(CLAUDE_CONFIG_DIR="$ftmp" node "$H/laconic-activate.js")"
  [ -e "$ftmp/.laconic-active" ] || fail "SessionStart deleted an unreadable flag ($bad) instead of leaving it"
  [ "$(cat "$ftmp/.laconic-active")" = "$before" ] || fail "SessionStart rewrote an unreadable flag ($bad)"
  [ -z "$bout3" ] || fail "SessionStart injected a register for an unreadable flag ($bad): [$bout3]"
done

# 17. A register that loses its own activation token to a colliding register still
# activates at a level IT owns. Detecting the collision and then falling back to
# FALLBACK_DEFAULT was no fix, because FALLBACK_DEFAULT is the contested token: the
# user asked for laconic and got the other register's voice under its statusline.
hij="$tmp/hijack"; mkdir -p "$hij/src/hooks" "$hij/registers/aaa" "$hij/registers/laconic"
cp "$H"/laconic-*.js "$hij/src/hooks/"
printf '%s' '{"id":"aaa","statusline":"AAA","tokens":{"aaa":"x","laconic":"stolen"},"reinforce":"AAA ACTIVE ({token})."}' > "$hij/registers/aaa/register.json"
printf '%s' 'aaa body' > "$hij/registers/aaa/register.md"
cp "$REPO_ROOT/plugins/laconic/registers/laconic/register.json" "$hij/registers/laconic/"
cp "$REPO_ROOT/plugins/laconic/registers/laconic/register.md" "$hij/registers/laconic/"
htmp="$tmp/hijack-cfg"; mkdir -p "$htmp"
printf '%s' '{"prompt":"/laconic"}' | CLAUDE_CONFIG_DIR="$htmp" node "$hij/src/hooks/laconic-mode-tracker.js" >/dev/null
hflag="$(cat "$htmp/.laconic-active" 2>/dev/null || echo none)"
[ "$hflag" != "laconic" ] || fail "bare /laconic resolved to a token another register owns"
hrein="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$htmp" node "$hij/src/hooks/laconic-mode-tracker.js")"
grep -q "AAA ACTIVE" <<<"$hrein" && fail "bare /laconic activated the colliding register's voice"
grep -q "LACONIC REGISTER ACTIVE" <<<"$hrein" || fail "bare /laconic did not activate the preferred register at all: flag=[$hflag]"

# 18. A registers/ dir that exists but cannot be read is NOT a bare install.
# fs.readdirSync reports EACCES the same way it reports a missing dir, and treating
# them alike sent a broken install down the hardcoded-level path, overwriting a flag
# the user set and injecting the generic anchor as though all were well.
noread="$tmp/noread"; mkdir -p "$noread/src/hooks" "$noread/registers"
cp "$H"/laconic-*.js "$noread/src/hooks/"
chmod 000 "$noread/registers"
ntmp="$tmp/noread-cfg"; mkdir -p "$ntmp"
printf '%s' 'laconic-ultra' > "$ntmp/.laconic-active"
nout="$(CLAUDE_CONFIG_DIR="$ntmp" node "$noread/src/hooks/laconic-activate.js")"
chmod 755 "$noread/registers"
grep -q "Elliptical but literate: drop the function words" <<<"$nout" && fail "unreadable registers/ fell back to the bare-install anchor"
[ "$(cat "$ntmp/.laconic-active" 2>/dev/null)" = "laconic-ultra" ] || fail "unreadable registers/ clobbered a held level"

# 19. A register with no `reinforce` still activates. The field is optional, so
# "no per-turn text" cannot be read as "the switch failed" — which is what the
# command file used to tell the model to say.
nor="$tmp/noreinforce"; mkdir -p "$nor/src/hooks" "$nor/registers/quiet"
cp "$H"/laconic-*.js "$nor/src/hooks/"
printf '%s' '{"id":"quiet","default":"off","statusline":"QUIET","tokens":{"quiet":"a","quiet-ultra":"b"}}' > "$nor/registers/quiet/register.json"
printf '%s' 'quiet body' > "$nor/registers/quiet/register.md"
qtmp="$tmp/noreinforce-cfg"; mkdir -p "$qtmp"
printf '%s' '{"prompt":"/laconic quiet-ultra"}' | CLAUDE_CONFIG_DIR="$qtmp" node "$nor/src/hooks/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$qtmp/.laconic-active" 2>/dev/null)" = "quiet-ultra" ] || fail "a register without 'reinforce' could not be activated"
qout="$(CLAUDE_CONFIG_DIR="$qtmp" node "$nor/src/hooks/laconic-activate.js")"
grep -q "QUIET REGISTER ACTIVE — level: quiet-ultra" <<<"$qout" || fail "a register without 'reinforce' did not inject its body"

# 20. An explicit off SURVIVES a following SessionStart while a level is configured.
# This is what recording the off buys: with the off spelled as flag absence, the
# default was indistinguishable from "never chose", so SessionStart re-applied it and
# the register came back a compaction after the user turned it off.
otmp="$tmp/off-durable"; mkdir -p "$otmp/xdg/laconic"
printf '%s' '{"defaultMode":"laconic-lite"}' > "$otmp/xdg/laconic/config.json"
CLAUDE_CONFIG_DIR="$otmp" XDG_CONFIG_HOME="$otmp/xdg" node "$H/laconic-activate.js" >/dev/null
printf '%s' '{"prompt":"/laconic off"}' | CLAUDE_CONFIG_DIR="$otmp" XDG_CONFIG_HOME="$otmp/xdg" node "$H/laconic-mode-tracker.js" >/dev/null
oout="$(CLAUDE_CONFIG_DIR="$otmp" XDG_CONFIG_HOME="$otmp/xdg" node "$H/laconic-activate.js")"
[ -z "$oout" ] || fail "SessionStart reactivated the register after an explicit off: [$(head -1 <<<"$oout")]"
orein="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$otmp" XDG_CONFIG_HOME="$otmp/xdg" node "$H/laconic-mode-tracker.js")"
[ -z "$orein" ] || fail "reinforcement resumed after an explicit off"

# 21. Bare `/laconic` on an install that cannot resolve a level must not DESTROY the
# level already held. It is the activation command; the one thing it cannot do is
# deactivate. Clearing here lost a standing choice permanently, and repairing the
# register data afterwards did not bring it back.
dtmp="$tmp/defective-held"; mkdir -p "$dtmp"
printf '%s' 'laconic' > "$dtmp/.laconic-active"
printf '%s' '{"prompt":"/laconic"}' | CLAUDE_CONFIG_DIR="$dtmp" node "$brk/src/hooks/laconic-mode-tracker.js" >/dev/null
[ "$(cat "$dtmp/.laconic-active" 2>/dev/null)" = "laconic" ] || fail "bare /laconic on a defective install destroyed the held level"
# and once the data is repaired, the level is still there
drein="$(printf '%s' '{"prompt":"hello"}' | CLAUDE_CONFIG_DIR="$dtmp" node "$H/laconic-mode-tracker.js")"
grep -q "LACONIC REGISTER ACTIVE (laconic)" <<<"$drein" || fail "held level did not survive a defective-install activation attempt"

# 22. `/laconic-ultra` and `/laconicfoo` are NOT `/laconic`. A bare prefix test read
# them as an argument-less activation, so a typo the UI rejects as an unknown command
# still turned the register on at a level nobody asked for.
for typo in "/laconic-ultra" "/laconicfoo"; do
  ttmp="$tmp/typo-$(echo "$typo" | tr -d '/-')"; mkdir -p "$ttmp"
  printf '%s' "{\"prompt\":\"$typo\"}" | CLAUDE_CONFIG_DIR="$ttmp" node "$H/laconic-mode-tracker.js" >/dev/null
  [ -e "$ttmp/.laconic-active" ] && fail "'$typo' activated the register: flag=[$(cat "$ttmp/.laconic-active")]"
done

# 23. The ownership test applies to the SESSION DEFAULT too, not only to a bare
# /laconic. A register sorting earlier that claims one of the preferred register's
# tokens would otherwise have SessionStart write that token and inject the OTHER
# register's body under its own statusline, on a plain install with nothing typed.
hij2="$tmp/hijack-default"; mkdir -p "$hij2/src/hooks" "$hij2/registers/aaa" "$hij2/registers/laconic"
cp "$H"/laconic-*.js "$hij2/src/hooks/"
printf '%s' '{"id":"aaa","statusline":"AAA","tokens":{"aaa":"x","laconic-lite":"stolen"},"reinforce":"AAA ACTIVE ({token})."}' > "$hij2/registers/aaa/register.json"
printf '%s' 'aaa body' > "$hij2/registers/aaa/register.md"
sed 's/"default": *"off"/"default": "laconic-lite"/' "$REPO_ROOT/plugins/laconic/registers/laconic/register.json" > "$hij2/registers/laconic/register.json"
cp "$REPO_ROOT/plugins/laconic/registers/laconic/register.md" "$hij2/registers/laconic/"
h2tmp="$tmp/hijack-default-cfg"; mkdir -p "$h2tmp"
h2out="$(CLAUDE_CONFIG_DIR="$h2tmp" node "$hij2/src/hooks/laconic-activate.js")"
grep -q "AAA REGISTER ACTIVE" <<<"$h2out" && fail "session default activated a colliding register's body"

# 24. The preservation rule for an unreadable flag holds under a configured LEVEL as
# well as under the shipped opt-in default. Only the opt-in arm was covered, which is
# how the overwrite on this path shipped green.
for bad in oversized unknown-token; do
  ltmp="$tmp/badflag-level-$bad"; mkdir -p "$ltmp"
  case "$bad" in
    oversized) head -c 200 /dev/zero | tr '\0' 'x' > "$ltmp/.laconic-active" ;;
    unknown-token) printf '%s' 'level-that-no-register-declares' > "$ltmp/.laconic-active" ;;
  esac
  lbefore="$(cat "$ltmp/.laconic-active")"
  CLAUDE_CONFIG_DIR="$ltmp" LACONIC_DEFAULT_MODE=laconic node "$H/laconic-activate.js" >/dev/null
  [ "$(cat "$ltmp/.laconic-active" 2>/dev/null)" = "$lbefore" ] || fail "a configured level overwrote an unreadable flag ($bad)"
done

# 25. `stop` and `disable` are reserved like the specials are. They are how the
# command surface spells deactivation, so a register declaring a level called `stop`
# produced a token env, config and bare activation all accepted while `/laconic stop`
# deactivated instead of selecting it.
res="$tmp/reserved"; mkdir -p "$res/src/hooks" "$res/registers/v"
cp "$H"/laconic-*.js "$res/src/hooks/"
printf '%s' '{"id":"v","default":"off","tokens":{"v":"a","stop":"b","disable":"c"}}' > "$res/registers/v/register.json"
printf '%s' 'v body' > "$res/registers/v/register.md"
node -e '
  const cfg = require(process.argv[1]);
  const leaked = ["stop", "disable"].filter(t => cfg.VALID_MODES.includes(t));
  if (leaked.length) {
    console.error("reserved names reachable as levels: " + JSON.stringify(leaked) + "; VALID_MODES " + JSON.stringify(cfg.VALID_MODES));
    process.exit(1);
  }
' "$res/src/hooks/laconic-config.js" || fail "a register declared a reserved name as a level"

echo "smoke-laconic: PASS (25 checks)"
