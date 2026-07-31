#!/usr/bin/env node
// laconic — shared config + hardened flag I/O.
//
// VALID_MODES is derived from the register registry (registers/*/) plus 'off',
// so adding a register file automatically makes its tokens valid — no list to
// keep in sync.
//
// Default-mode resolution order:
//   1. LACONIC_DEFAULT_MODE env var
//   2. $XDG_CONFIG_HOME/laconic/config.json (or ~/.config/laconic/config.json,
//      or %APPDATA%\laconic\config.json) "defaultMode" field
//   3. the default register's `default` field, which may be a level token or a
//      special like 'off'. With no register data at all (a bare hook install) this
//      falls back to 'laconic'; with a registers/ dir that loaded nothing it
//      resolves to the special instead, because a level no register defines would
//      activate a register this install does not have.
//
// A level already recorded in the flag file outranks all three. These answer "what
// should a session with no choice recorded start as", not "what is active now".
//
// The shipped register declares a special rather than a level, so nothing is
// injected until someone asks for it (see registers/laconic/register.json rather
// than trusting this comment for the current value). getActivationLevel() answers
// the different question of WHICH level an explicit `/laconic` turns on.
//
// The flag I/O below is a clean-room implementation of the symlink-safe,
// size-capped, whitelist-validated pattern: refuse a symlink at the flag path
// itself, refuse a symlinked immediate parent unless it resolves to a dir the
// current user owns, write atomically via temp+rename with O_NOFOLLOW and 0600,
// cap reads, and reject any value not on VALID_MODES. Read, write and clear all
// go through the same parent gate (safeRealDir).
//
// Scope of that guarantee, stated precisely because the previous wording
// overclaimed it:
//   - Only the IMMEDIATE parent is examined, and lstat only inspects a path's
//     final component. A symlinked ANCESTOR above that parent is not detected,
//     so the uid gate is bypassable by an attacker who controls one.
//   - The ownership check applies only on the symlink branch. A plain parent
//     directory is accepted without an ownership test, world-writable or not.
//   - On Windows there is no O_NOFOLLOW and no uid check, so the lstat is the
//     only guard and the TOCTOU window has no backstop.
// Tracked in issue #55. What it does reliably buy: the read result is validated
// against VALID_MODES before it is returned, so even a fully successful attack
// yields a known short token rather than secret bytes reaching model context.

const fs = require('fs');
const path = require('path');
const os = require('os');
const registry = require('./laconic-registry');

// Derived from the registry rather than restated, so a special a register may
// declare as its `default` is always on this whitelist. The guards on every value
// taken from the registry in this section are not defensive padding: this all
// executes at module load, outside every try/catch in this file, so against a
// stale or partially-updated laconic-registry.js a missing export throws a
// TypeError and both hooks exit non-zero — the one outcome the whole file is
// written to avoid. The literals are floors for that mismatched-install case only;
// the derived values are what normally apply.
const SPECIAL_MODES = Array.isArray(registry.SPECIAL_DEFAULTS) ? registry.SPECIAL_DEFAULTS.slice() : ['off'];
// The special that means "not active". Named once rather than written as a literal
// at each use: three separate `=== 'off'` comparisons had already drifted out of
// step with SPECIAL_MODES, so a renamed special left the hooks writing a flag no
// register could resolve and reading a deactivation request as a level.
const OFF_MODE = SPECIAL_MODES.length ? SPECIAL_MODES[0] : 'off';
// Four roles, deliberately unchanged when the shipped register went opt-in:
//   1. the default mode for a BARE hook install, where registers/ is absent and
//      there is no register data to express an intent with;
//   2. the id of the PREFERRED register in registryDefault() below;
//   3. the same preference lookup again in getActivationLevel();
//   4. that function's terminal fallback when no register can supply a level.
// Setting it to 'off' would break all four: no register has the id 'off', so both
// preference lookups would silently fall back to registers[0], and (4) would hand
// back the one value an activation must never resolve to. (1) is the single path
// where a level is the only useful answer. Whether the shipped register
// auto-activates is register data, so it lives in register.json's `default`.
const FALLBACK_DEFAULT = 'laconic';
// Derived from the registry's token bound rather than restated, so the two cannot
// drift. If this cap were ever the smaller of the two, a token the registry accepts
// would be refused by safeWriteFlag, which validates against the same constant: the
// level would be unsettable, and /laconic <level> would no-op on a token the
// register legitimately declares.
//
// Guarded for the same mismatched-install reason as SPECIAL_MODES, with a different
// failure shape: undefined here does not throw, it disables the cap. `n > undefined`
// is false, so safeWriteFlag accepts any length, while readFlag's
// Buffer.alloc(undefined) throws into a catch that returns null. The flag gets
// written and every read of it refused: the level looks set and nothing reinforces.
const MAX_FLAG_BYTES = typeof registry.MAX_TOKEN_BYTES === 'number' ? registry.MAX_TOKEN_BYTES : 64;

// Registry loaded once at module load. VALID_MODES = specials ∪ tokens ∪ aliases.
const REG = (() => { try { return registry.loadRegisters(); } catch (e) { return null; } })();

// The hooks read the same load rather than scanning registers/ again: both used to
// call loadRegisters() a second time, which doubled the filesystem work on every
// turn and printed every registry diagnostic twice. A hook process handles one
// event and exits, so this cannot go stale within a run.
function getRegistry() {
  return REG;
}

const VALID_MODES = (() => {
  const modes = SPECIAL_MODES.slice();
  // try/catch for the same mismatched-install reason as the guards above, and
  // stated here because the guard on SPECIAL_DEFAULTS alone was narrower than its
  // own comment claimed: a laconic-registry.js missing only SPECIAL_DEFAULTS
  // survived, while one also missing allTokens/allAliases still exited non-zero
  // from this line. Losing the token list costs the register; throwing costs the
  // session.
  try {
    if (REG) modes.push(...registry.allTokens(REG), ...registry.allAliases(REG));
  } catch (e) { /* registry mismatch — specials plus the fallback still resolve */ }
  // FALLBACK_DEFAULT must be on the whitelist even when the registry yields no
  // tokens (registers/ absent or every register rejected). getDefaultMode() ->
  // registryDefault() returns it unconditionally in that case, so omitting it
  // here makes the hooks write a flag that readFlag() then refuses: activation
  // silently no-ops and /laconic <level> rejects its own default. That is the
  // documented bare-hook-install path, so it has to validate.
  if (!modes.includes(FALLBACK_DEFAULT)) modes.push(FALLBACK_DEFAULT);
  return Array.from(new Set(modes));
})();

// Opt-in diagnostics, same channel and same reason as laconic-registry.js: with
// the register shipping opt-in, "nothing injected" is the healthy state, so a
// genuine resolution failure looks exactly like a correct default install. This
// is the only place that tells them apart.
//
// Defined here as well as in the registry, and exported so the two hooks share one
// copy rather than inlining the env test a third time. It cannot be defined in one
// module only: the registry must not require this file back, which would be a
// cycle. Both read the environment at call time, so they cannot skew in value.
function debugOn() {
  return process.env.LACONIC_DEBUG === '1';
}

function getConfigDir() {
  if (process.env.XDG_CONFIG_HOME) return path.join(process.env.XDG_CONFIG_HOME, 'laconic');
  if (process.platform === 'win32') {
    return path.join(process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming'), 'laconic');
  }
  return path.join(os.homedir(), '.config', 'laconic');
}

function getConfigPath() {
  return path.join(getConfigDir(), 'config.json');
}

// The default register's default token, or the hardcoded fallback.
function registryDefault() {
  if (!REG || !REG.registers.length) {
    // A registers/ dir that exists and yielded nothing is a defect in the data,
    // not a bare install: every register in it was rejected (unparseable
    // register.json, missing register.md, no valid tokens). Returning
    // FALLBACK_DEFAULT there would activate at a level no register defines, on an
    // install whose data asks to be opt-in, and the stub body would make it look
    // like the plugin was working. Refuse instead; LACONIC_DEBUG=1 says why.
    if (REG && REG.dirPresent) {
      if (debugOn()) {
        // The per-register reason has already printed from laconic-registry.js, so
        // this line says what the consequence is and nothing more. It used to end
        // with "run with LACONIC_DEBUG=1 to see which", which only a reader who had
        // already done that could see.
        process.stderr.write('[laconic] config: registers/ is present but no register in it loaded; staying off\n');
      }
      return OFF_MODE;
    }
    return FALLBACK_DEFAULT;
  }
  const preferred = REG.registers.find(r => r.id === FALLBACK_DEFAULT) || REG.registers[0];
  if (debugOn() && preferred.id !== FALLBACK_DEFAULT) {
    process.stderr.write(`[laconic] config: no register with id '${FALLBACK_DEFAULT}'; using '${preferred.id}' as the preferred register\n`);
  }
  // Same ownership test as getActivationLevel(), because the hijack it prevents is
  // reachable from here too: a register sorting earlier that claims one of this
  // register's tokens would have SessionStart write that token and then inject the
  // OTHER register's body under its own statusline, on a plain default install with
  // no /laconic typed at all. A `default` naming a token the register lost is not a
  // usable default, so fall through to the activation path, which picks among the
  // tokens it still owns.
  const def = preferred.default;
  if (SPECIAL_MODES.includes(def)) return def;
  if (REG.tokenMap[def] === preferred) return def;
  if (debugOn()) {
    process.stderr.write(`[laconic] config: '${preferred.id}' does not own its declared default '${def}' after collision resolution\n`);
  }
  return OFF_MODE;
}

// Resolve the session default and say WHERE it came from. The source matters for
// one caller: a resolved 'off' means different things depending on origin. From
// the env var or the user's config file it is an explicit request to be off, so
// SessionStart clears the flag. From register data it only means "do not
// auto-activate on install", and SessionStart also fires on resume, clear and
// compact, so treating that as a request to be off would delete a level the user
// turned on with /laconic — at exactly the compaction the register promises to
// survive. See laconic-activate.js.
function resolveDefaultMode() {
  const envMode = process.env.LACONIC_DEFAULT_MODE;
  if (envMode && VALID_MODES.includes(envMode.toLowerCase())) {
    return { mode: envMode.toLowerCase(), source: 'env' };
  }

  try {
    const config = JSON.parse(fs.readFileSync(getConfigPath(), 'utf8'));
    if (config && config.defaultMode && VALID_MODES.includes(String(config.defaultMode).toLowerCase())) {
      return { mode: String(config.defaultMode).toLowerCase(), source: 'config' };
    }
  } catch (e) { /* missing/invalid config — fall through */ }

  return { mode: registryDefault(), source: 'register' };
}

function getDefaultMode() {
  return resolveDefaultMode().mode;
}

// The level an explicit activation should switch to: `/laconic` with no
// argument, or the skill entering the register. Distinct from getDefaultMode(),
// which answers "should this session start in the register at all" and may
// legitimately answer a special like 'off'.
//
// No LEVEL this returns may be a special: every candidate is tested against
// SPECIAL_MODES rather than against the literal 'off', so adding a second special
// cannot reintroduce the case where the documented activation command deactivates.
// `registry.tokenOk` also reserves those names, so a register cannot declare a level
// called 'off' in the first place; the tests here are the second line, not the only
// one.
//
// The one deliberate exception is the terminal case: an install with a registers/ dir
// that loaded nothing has no level to offer, and this says so by returning OFF_MODE.
// Callers must treat that as "cannot activate", NOT as "deactivate" — laconic-mode-
// tracker.js leaves the flag untouched on it, because clearing there destroyed a held
// level on the activation command.
function getActivationLevel() {
  const mode = getDefaultMode();
  if (!SPECIAL_MODES.includes(mode)) return mode;
  if (REG && REG.registers.length) {
    const preferred = REG.registers.find(r => r.id === FALLBACK_DEFAULT) || REG.registers[0];
    // Ownership, not mere validity, and then a token the register actually OWNS.
    // VALID_MODES is the union across every register, so a token the preferred
    // register declares but LOST to a collision passes an includes() test: a
    // register sorting earlier that claims the token `laconic` would make an
    // argument-less /laconic write `laconic` and resolve to that other register's
    // voice, under that register's statusline. Testing ownership and then falling
    // back to FALLBACK_DEFAULT was no fix at all, because FALLBACK_DEFAULT is the
    // contested token itself: the substitution has to come from this register's
    // own surviving tokens.
    const owned = preferred.tokens.filter(t => REG.tokenMap[t] === preferred && !SPECIAL_MODES.includes(t));
    if (owned.length) {
      if (owned.includes(preferred.activationToken)) return preferred.activationToken;
      if (debugOn()) {
        process.stderr.write(`[laconic] config: '${preferred.id}' lost its activation token '${preferred.activationToken}' to another register; activating at '${owned[0]}' instead\n`);
      }
      return owned[0];
    }
    if (debugOn()) {
      process.stderr.write(`[laconic] config: '${preferred.id}' owns none of its declared tokens after collision resolution\n`);
    }
  }
  // Nothing this install can activate. A registers/ dir that is present and
  // produced nothing is a defect, and answering with FALLBACK_DEFAULT there just
  // moves the lie one command later: /laconic would write a level no register
  // defines and the next SessionStart would inject the generic anchor as though
  // the register were working. Refuse. Only a genuinely bare hook install, with no
  // registers/ at all, gets the hardcoded level, which is the case the anchor text
  // exists for.
  if (REG && REG.dirPresent) return OFF_MODE;
  return FALLBACK_DEFAULT;
}

// Resolve a flag dir that may itself be a symlink (legit: ~/.claude symlinked
// elsewhere). Returns the real dir if safe (owned by current user on Unix, or
// under home on Windows), else null. Non-symlink dirs pass through unchanged.
function safeRealDir(dir) {
  try {
    const lstat = fs.lstatSync(dir);
    if (!lstat.isSymbolicLink()) return dir;
    const real = fs.realpathSync(dir);
    const st = fs.statSync(real);
    if (!st.isDirectory()) return null;
    if (typeof process.getuid === 'function') {
      return st.uid === process.getuid() ? real : null;
    }
    const home = path.resolve(os.homedir()).toLowerCase();
    const r = path.resolve(real).toLowerCase();
    return (r === home || r.startsWith(home + path.sep)) ? real : null;
  } catch (e) {
    return null;
  }
}

// Symlink-safe atomic flag write. Silent-fails (flag is best-effort).
function safeWriteFlag(flagPath, content) {
  try {
    // Refuse to persist anything readFlag would reject. The write and read sides
    // were previously asymmetric: write accepted any string while read enforced
    // both a size cap and the whitelist, so a mode arriving from env, config, or
    // a user-supplied register could be written and then rejected on every read.
    // The flag would sit on disk looking correct while activation silently
    // no-opped. Validating here makes an unreadable flag unwritable.
    const value = String(content);
    if (!VALID_MODES.includes(value) || Buffer.byteLength(value, 'utf8') > MAX_FLAG_BYTES) return;

    const dir = path.dirname(flagPath);
    fs.mkdirSync(dir, { recursive: true });
    const realDir = safeRealDir(dir);
    if (!realDir) return;

    const realFlagPath = path.join(realDir, path.basename(flagPath));
    try {
      if (fs.lstatSync(realFlagPath).isSymbolicLink()) return; // the clobber vector
    } catch (e) {
      if (e.code !== 'ENOENT') return;
    }

    const tempPath = path.join(realDir, `.laconic-active.${process.pid}.${Date.now()}`);
    const O_NOFOLLOW = typeof fs.constants.O_NOFOLLOW === 'number' ? fs.constants.O_NOFOLLOW : 0;
    const flags = fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | O_NOFOLLOW;
    let fd;
    try {
      fd = fs.openSync(tempPath, flags, 0o600);
      fs.writeSync(fd, String(content));
      try { fs.fchmodSync(fd, 0o600); } catch (e) { /* best-effort */ }
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
    }
    fs.renameSync(tempPath, realFlagPath);
  } catch (e) { /* silent — best-effort */ }
}

// Symlink-safe, size-capped, whitelist-validated flag read. Returns a valid
// mode string or null on any anomaly.
function readFlag(flagPath) {
  try {
    // Resolve the parent through the same gate safeWriteFlag uses. Checking only
    // the flag path catches a symlinked FLAG but not a symlinked PARENT, so a
    // hostile ~/.claude -> attacker-owned dir would be read from despite the
    // header promising parent-dir safety. safeRealDir returns null unless the
    // resolved dir is owned by the current user, so an unsafe parent yields
    // nothing rather than a read.
    const realDir = safeRealDir(path.dirname(flagPath));
    if (!realDir) return null;
    const realFlagPath = path.join(realDir, path.basename(flagPath));

    let st;
    try { st = fs.lstatSync(realFlagPath); } catch (e) { return null; }
    if (st.isSymbolicLink() || !st.isFile() || st.size > MAX_FLAG_BYTES) return null;

    const O_NOFOLLOW = typeof fs.constants.O_NOFOLLOW === 'number' ? fs.constants.O_NOFOLLOW : 0;
    let fd, out;
    try {
      fd = fs.openSync(realFlagPath, fs.constants.O_RDONLY | O_NOFOLLOW);
      const buf = Buffer.alloc(MAX_FLAG_BYTES);
      const n = fs.readSync(fd, buf, 0, MAX_FLAG_BYTES, 0);
      out = buf.slice(0, n).toString('utf8');
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
    }

    const raw = out.trim().toLowerCase();
    return VALID_MODES.includes(raw) ? raw : null;
  } catch (e) {
    return null;
  }
}

// Symlink-safe flag removal. Silent-fails (clearing is best-effort), but goes
// through the same parent gate as write and read: callers previously used a raw
// fs.unlinkSync(flagPath), which resolved nothing, so a hostile parent symlink
// could redirect the delete at a file of the same name in the attacker's target
// directory. Damage was bounded (the basename is fixed) but the gate was simply
// absent on this path while present on the other two.
function safeClearFlag(flagPath) {
  try {
    const realDir = safeRealDir(path.dirname(flagPath));
    if (!realDir) return;
    fs.unlinkSync(path.join(realDir, path.basename(flagPath)));
  } catch (e) { /* silent — best-effort */ }
}

module.exports = { getDefaultMode, resolveDefaultMode, getActivationLevel, getConfigDir, getConfigPath, VALID_MODES, SPECIAL_MODES, OFF_MODE, debugOn, getRegistry, safeWriteFlag, readFlag, safeClearFlag, registryDefault };
