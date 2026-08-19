#!/usr/bin/env node
// laconic — Claude Code UserPromptSubmit hook.
//   1. Handle /laconic [level|off] commands + "stop laconic" / "normal mode".
//   2. Emit the active register's per-turn reinforcement so the register stays
//      in the model's attention every turn (survives compaction, resists other
//      plugins' competing style injections).

const path = require('path');
const os = require('os');
const { getActivationLevel, safeWriteFlag, readFlag, safeClearFlag, VALID_MODES, SPECIAL_MODES, OFF_MODE, debugOn, getRegistry } = require('./laconic-config');
const registry = require('./laconic-registry');

const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const flagPath = path.join(claudeDir, '.laconic-active');

// Deactivation RECORDS itself rather than deleting the flag. Absence of a flag means
// "no choice made yet", which is what lets a configured default seed a session, so
// spelling "the user turned it off" as absence made the two indistinguishable: with
// LACONIC_DEFAULT_MODE or config.json naming a level, `/laconic off` deleted the flag
// and the next compaction read the default and switched the register back on. A
// recorded special is a standing choice, and SessionStart honors it like any other.
//
// safeClearFlag is attempted as a fallback when the write does not land, but it is not
// a guarantee: both calls go through the same safeRealDir parent gate, so on the
// failure that gate causes (an unowned or hostile parent dir) neither one does
// anything and a previously recorded level stays on disk. Nothing this hook can do
// from inside that state fixes it; what it does buy is the ordinary case, where the
// write fails for a reason the clear does not share.
function setOff() {
  safeWriteFlag(flagPath, OFF_MODE);
  if (readFlag(flagPath) !== OFF_MODE) safeClearFlag(flagPath);
}

let input = '';
process.stdin.on('data', chunk => { input += chunk; });
// Broken pipe / parent crash emits 'error'; without a listener Node throws it
// uncaught and the hook exits non-zero. Hooks must always exit 0.
process.stdin.on('error', () => process.exit(0));
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    let prompt = (data.prompt || '').trim().toLowerCase().replace(/\s+/g, ' ');

    // Claude Code delivers a slash command to this hook as an envelope rather
    // than the literal command:
    //   <command-message>laconic</command-message>
    //   <command-name>/laconic:laconic</command-name>
    //   <command-args>laconic</command-args>
    // The whitespace collapse above normalizes the one-line and newline forms
    // into the same string; <command-args> may be empty or absent. Every switch
    // below matches a literal command, so without this reconstruction every
    // slash invocation was a silent no-op, including `/laconic off`.
    //
    // The name arrives namespaced as `/laconic:laconic` when the plugin and the
    // command share a name, so the match allows an optional `:<command>` suffix.
    // A foreign command's envelope is left alone, and natural-language detection
    // is skipped for it so another command's arguments cannot trip our own
    // activation or deactivation triggers. Same shape as caveman's tracker.
    let skipNaturalLanguage = false;
    const envName = /<command-name>\s*([^<\s]+)\s*<\/command-name>/.exec(prompt);
    if (envName) {
      if (/^\/laconic(:[a-z0-9-]+)?$/.test(envName[1])) {
        const envArgs = /<command-args>\s*([^<]*?)\s*<\/command-args>/.exec(prompt);
        const args = envArgs ? envArgs[1].trim() : '';
        prompt = args ? envName[1] + ' ' + args : envName[1];
      } else {
        skipNaturalLanguage = true;
      }
    }

    // Deactivation intent, computed first so "turn laconic off" never falls
    // through to activation.
    // skipNaturalLanguage is set when a FOREIGN command's envelope was seen, so
    // another command's arguments cannot read as a request to turn this register
    // off. An explicit `/laconic off` still reaches the switch below, because the
    // reconstruction above rewrites it into a literal command string.
    const wantsOff =
      !skipNaturalLanguage &&
      (/\b(stop|disable|deactivate|turn off)\s+(the\s+)?laconic\b/.test(prompt) ||
      /\blaconic\s+(off|stop|disabled?)\b/.test(prompt) ||
      /^(please\s+)?(go\s+|back\s+to\s+|switch\s+(back\s+)?to\s+|return\s+to\s+)?normal\s+mode\b/.test(prompt));

    // /laconic [level|off] — explicit switch. The boundary matters: a bare
    // startsWith('/laconic') also matched `/laconic-ultra` and `/laconicfoo`, which
    // parse as an argument-less activation, so a mistyped command that the UI
    // rejects as unknown still turned the register on at a level nobody asked for.
    if (/^\/laconic(:[a-z0-9-]+)?(\s|$)/.test(prompt)) {
      const arg = prompt.split(' ')[1] || '';
      let mode = null;
      // Bare `/laconic` asks to turn the register ON, so it resolves through
      // getActivationLevel(), not getDefaultMode(). The shipped register's
      // session default is 'off'; reading the session default here would make
      // the documented activation command deactivate instead.
      // A bare /laconic can legitimately fail to resolve: on an install whose
      // registers/ dir is present but yielded nothing, there is no level to switch
      // into, and getActivationLevel() answers with a special rather than naming a
      // level no register defines.
      if (!arg) mode = getActivationLevel();
      // Any special is a request to leave the register, not a level to switch to:
      // matched by membership, and written through OFF_MODE, so a renamed special
      // cannot become a flag value no register can resolve. `/laconic <special>`
      // used to write the literal 'off', which safeWriteFlag then rejected as
      // off-whitelist, leaving the register on after the user asked for it off.
      else if (arg === 'stop' || arg === 'disable' || SPECIAL_MODES.includes(arg)) mode = OFF_MODE;
      else if (VALID_MODES.includes(arg)) mode = arg;
      // Unknown arg leaves the flag untouched (no silent overwrite). That silence
      // is deliberate but total, so the one diagnostic channel says what happened.
      else if (debugOn()) {
        process.stderr.write(`[laconic] mode-tracker: '${arg}' is not a known level; flag left unchanged (valid: ${VALID_MODES.join(', ')})\n`);
      }
      if (!arg && mode && SPECIAL_MODES.includes(mode)) {
        // Bare `/laconic` could not resolve a level: registers/ is present but
        // nothing loaded from it. This is a request to turn the register ON, so the
        // one thing it must not do is turn a held level OFF. Leave the flag exactly
        // as it is — clearing here destroyed a standing choice permanently, on the
        // command whose whole job is activation, and repairing the register data
        // afterwards did not bring the level back.
        if (debugOn()) {
          process.stderr.write('[laconic] mode-tracker: nothing to activate; this install has a registers/ dir but no register loaded from it; leaving the flag unchanged\n');
        }
      } else if (mode && SPECIAL_MODES.includes(mode)) {
        setOff();
      } else if (mode) safeWriteFlag(flagPath, mode);
    } else if (wantsOff) {
      setOff();
    }

    // Per-turn reinforcement from the active register. readFlag enforces
    // symlink-safe read + size cap + VALID_MODES whitelist, so a missing,
    // corrupted, oversized, or symlinked flag yields null and we emit nothing.
    const activeMode = readFlag(flagPath);
    if (activeMode) {
      let reinforce = null;
      try {
        const reg = getRegistry();
        const r = registry.resolve(reg, activeMode);
        if (r && r.register.reinforce) {
          reinforce = r.register.reinforce.replace(/\{token\}/g, r.token);
        }
      } catch (e) { /* emit nothing on failure */ }

      if (reinforce) {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: "UserPromptSubmit",
            additionalContext: reinforce
          }
        }));
      }
    }
  } catch (e) {
    // Silent fail — never block a turn.
  }
});
