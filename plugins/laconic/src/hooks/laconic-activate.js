#!/usr/bin/env node
// laconic — Claude Code SessionStart hook.
//   1. Decide the active level: the one already on the flag if there is one, else
//      the resolved session default (see the resolution block below).
//   2. Write the active flag at $CLAUDE_CONFIG_DIR/.laconic-active if it changed.
//   3. Emit the register body (filtered to the active level) as SessionStart
//      context so the register anchors from turn one.
// Emits nothing at all when nothing is active, because SessionStart stdout becomes
// session context: a default install should cost zero tokens, not a placeholder.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { resolveDefaultMode, safeWriteFlag, readFlag, safeClearFlag, SPECIAL_MODES, debugOn, getRegistry } = require('./laconic-config');
const registry = require('./laconic-registry');

// "Is there a file here at all", answered without caring whether the contents are
// usable. Distinguishes "no flag" from "a flag readFlag refused", which the resolution
// below has to treat differently.
//
// lstat spares only the FINAL component: a symlink at the flag path itself is reported
// as a symlink rather than followed, but symlinked ancestor directories are traversed
// normally, and this does not go through the safeRealDir parent gate that read, write
// and clear share. The answer is therefore weaker than readFlag's, which is acceptable
// because it is only ever used to decide whether to LEAVE a file alone. Do not reuse it
// for anything that acts on the path.
function flagPresent(p) {
  try {
    fs.lstatSync(p);
    return true;
  } catch (e) {
    return false;
  }
}

// Filter a register body to a single level: drop OTHER levels' intensity-table
// rows and "- level:" example lines, keep everything else.
//
// Both matchers are gated on `tokens` — the level names the register actually
// declares — because the shapes they look for are not unique to level lines.
// `/^- (\S+?):\s/` alone also matches an ordinary prose bullet whose first word
// ends in a colon, so `- **Keep**: logic connectives (because, so, but...)` in
// registers/laconic/register.md read as "an example line for a level called
// **Keep**" and was stripped at EVERY level. The register kept its "Drop" rule
// and silently lost the "Keep" guardrail that balances it. Gating on the
// declared tokens means a line is only treated as level-keyed when its key is
// a real level, so prose falls through to the keep branch.
//
// The gate trades one failure for a strictly louder one. A row or example line
// keyed to a token the register no longer declares (renamed in register.json,
// left behind in register.md) is no longer dropped: it now survives into the
// injected body at every level, where a reader sees a stale rule next to a header
// naming a different level. That is visible. What it replaces was silent deletion
// of whatever prose happened to match the shape, which is how the "Keep" rule
// disappeared for however long it did. Prefer the failure that shows.
//
// An empty or missing `tokens` therefore recognizes nothing and keeps everything,
// rather than treating the active level as the only known one: under-filtering
// leaks every level's rows at once, which is loud, while the old fallback silently
// stripped the other levels' lines and looked correct. loadOne() guarantees a
// non-empty array, so this is a floor, not a live path.
function filterToLevel(text, level, tokens) {
  const levels = new Set(Array.isArray(tokens) ? tokens : []);
  return text.split('\n').reduce((acc, line) => {
    const row = line.match(/^\|\s*\*\*(\S+?)\*\*\s*\|/);
    if (row && levels.has(row[1])) { if (row[1] === level) acc.push(line); return acc; }
    const ex = line.match(/^- (\S+?):\s/);
    if (ex && levels.has(ex[1])) { if (ex[1] === level) acc.push(line); return acc; }
    acc.push(line);
    return acc;
  }, []).join('\n');
}

const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const flagPath = path.join(claudeDir, '.laconic-active');

const { mode, source } = resolveDefaultMode();

// One rule, applied on every path: a valid level already on the flag is the
// user's standing choice, and a DEFAULT does not revoke it. Defaults seed a
// session that has no choice recorded yet. This matters because SessionStart fires
// on resume, clear and compact as well as startup (plugin.json sets no matcher),
// so anything this hook does to the flag, it does again at every compaction. Two
// bugs came out of applying that rule to only part of the space: a register-
// sourced 'off' deleted an active level, and a configured LEVEL overwrote one
// (config `{"defaultMode":"laconic-lite"}` plus /laconic laconic-ultra reverted to
// laconic-lite at the next compaction).
//
// The one thing that does override the flag is a special the user asked for
// explicitly, through the env var or the config file. That is a kill switch, and a
// kill switch that a stale flag could veto would not be one.
//
// A flag that is PRESENT but unreadable (oversized, a symlink, or naming a token
// no register declares any more) is left exactly where it is. It is not a
// standing choice this hook can act on, but it is also not this hook's to delete:
// a register.json that is briefly unparseable mid-edit would otherwise cost the
// user their level permanently.
let active = null;
if (SPECIAL_MODES.includes(mode) && source !== 'register') {
  // Kill switch. The flag is rewritten rather than deleted so the state stays
  // explicit, and cleared only if the write could not land.
  safeWriteFlag(flagPath, mode);
  if (readFlag(flagPath) !== mode) safeClearFlag(flagPath);
} else {
  const held = readFlag(flagPath);
  if (held && !SPECIAL_MODES.includes(held)) {
    active = held; // a level, already on disk; nothing to write
  } else if (held) {
    // A RECORDED special: the user asked for off. That is a standing choice too, so
    // a configured default does not overturn it. Without this, `/laconic off` under a
    // configured level lasted until the next compaction and then silently undid
    // itself.
    if (debugOn()) {
      process.stderr.write(`[laconic] activate: flag records '${held}'; leaving the register off despite a ${source} default of '${mode}'\n`);
    }
  } else if (flagPresent(flagPath)) {
    // Present but unreadable: oversized, a symlink, or naming a token no register
    // declares any more. Not a choice this hook can act on, and not this hook's to
    // overwrite either — a register.json unparseable mid-edit would otherwise cost
    // the user their level the moment a default was configured. Explicit
    // `/laconic <level>` still replaces it, so the user is never stuck.
    if (debugOn()) {
      process.stderr.write('[laconic] activate: flag at ' + flagPath + ' is present but unreadable; leaving it untouched and staying off\n');
    }
  } else if (!SPECIAL_MODES.includes(mode)) {
    active = mode;
    safeWriteFlag(flagPath, mode);
    // The write is best-effort and silent by design (a symlinked flag, an unowned
    // parent). Injecting the register while nothing persists would leave SessionStart
    // and UserPromptSubmit disagreeing every turn of the session, so say so on the
    // one channel there is.
    if (readFlag(flagPath) !== mode && debugOn()) {
      process.stderr.write('[laconic] activate: could not persist the active level to ' + flagPath + '; the register will not reinforce per turn this session\n');
    }
  }
}

if (!active) {
  process.exit(0);
}

const reg = getRegistry();
const resolved = reg ? registry.resolve(reg, active) : null;

if (resolved) {
  const { register, token } = resolved;
  process.stdout.write(
    register.statusline + ' REGISTER ACTIVE — level: ' + token + '\n\n' +
    filterToLevel(register.body, token, register.tokens)
  );
} else if (reg && reg.dirPresent) {
  // registers/ is right there and produced nothing usable: unparseable
  // register.json, missing register.md, no valid tokens, or a dir we cannot read.
  // The anchor below would describe a register this install does not actually
  // have, which is the failure that looks most like success. Say nothing.
  if (debugOn()) {
    process.stderr.write('[laconic] activate: registers/ is present but nothing in it resolved; injecting nothing rather than the generic anchor\n');
  }
} else {
  // Registry unresolvable because this install ships no registers/ dir at all
  // (a bare hook install). Minimal anchor so the register still applies.
  process.stdout.write(
    'LACONIC REGISTER ACTIVE — level: ' + active + '\n\n' +
    'Elliptical but literate: drop the function words a reader restores for free, ' +
    'keep the logic connectives, notebook symbols where they decode instantly. ' +
    'Full prose on high-value turns; compress only the final statement. ' +
    'Compresses the report, never the work: files read, checks run, claims verified, ' +
    'and scope finished are identical at every level. State which claims are verified ' +
    'and which are assumed.'
  );
}
