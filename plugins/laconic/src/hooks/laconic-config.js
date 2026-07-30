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
//   3. the default register's `default` field, which may be a level token or
//      'off' (falls back to 'laconic' only when there is no register data at all)
//
// The shipped register declares 'off', so nothing is injected until someone asks
// for it. getActivationLevel() answers the different question of WHICH level an
// explicit `/laconic` turns on.
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
// declare as its `default` is always on this whitelist.
const SPECIAL_MODES = registry.SPECIAL_DEFAULTS.slice();
// Dual role, deliberately unchanged when the shipped register went opt-in:
//   1. the default mode for a BARE hook install, where registers/ is absent and
//      there is no register data to express an intent with;
//   2. the id of the PREFERRED register in registryDefault() below.
// Setting it to 'off' would break (2) — no register has the id 'off', so the
// preference lookup would silently fall back to registers[0] — and (1) is the
// one path where a level is the only useful answer. Whether the register
// auto-activates is register data, so it lives in register.json's `default`.
const FALLBACK_DEFAULT = 'laconic';
// Derived from the registry's token bound rather than restated, so the two
// cannot drift. If the read cap were ever the smaller of the two, a token the
// registry accepts could be written and then never read back.
const MAX_FLAG_BYTES = registry.MAX_TOKEN_BYTES;

// Registry loaded once at module load. VALID_MODES = specials ∪ tokens ∪ aliases.
const REG = (() => { try { return registry.loadRegisters(); } catch (e) { return null; } })();

const VALID_MODES = (() => {
  const modes = SPECIAL_MODES.slice();
  if (REG) modes.push(...registry.allTokens(REG), ...registry.allAliases(REG));
  // FALLBACK_DEFAULT must be on the whitelist even when the registry yields no
  // tokens (registers/ absent or every register rejected). getDefaultMode() ->
  // registryDefault() returns it unconditionally in that case, so omitting it
  // here makes the hooks write a flag that readFlag() then refuses: activation
  // silently no-ops and /laconic <level> rejects its own default. That is the
  // documented bare-hook-install path, so it has to validate.
  if (!modes.includes(FALLBACK_DEFAULT)) modes.push(FALLBACK_DEFAULT);
  return Array.from(new Set(modes));
})();

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
  if (!REG || !REG.registers.length) return FALLBACK_DEFAULT;
  const preferred = REG.registers.find(r => r.id === FALLBACK_DEFAULT) || REG.registers[0];
  return preferred.default;
}

function getDefaultMode() {
  const envMode = process.env.LACONIC_DEFAULT_MODE;
  if (envMode && VALID_MODES.includes(envMode.toLowerCase())) return envMode.toLowerCase();

  try {
    const config = JSON.parse(fs.readFileSync(getConfigPath(), 'utf8'));
    if (config && config.defaultMode && VALID_MODES.includes(String(config.defaultMode).toLowerCase())) {
      return String(config.defaultMode).toLowerCase();
    }
  } catch (e) { /* missing/invalid config — fall through */ }

  return registryDefault();
}

// The level an explicit activation should switch to: `/laconic` with no
// argument, or the skill entering the register. Distinct from getDefaultMode(),
// which answers "should this session start in the register at all" and may
// legitimately answer 'off'. Asking for the register can never resolve to 'off',
// so bare `/laconic` falls through to the register's own activationToken.
function getActivationLevel() {
  const mode = getDefaultMode();
  if (mode !== 'off') return mode;
  if (REG && REG.registers.length) {
    const preferred = REG.registers.find(r => r.id === FALLBACK_DEFAULT) || REG.registers[0];
    if (preferred.activationToken && VALID_MODES.includes(preferred.activationToken)) {
      return preferred.activationToken;
    }
  }
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

module.exports = { getDefaultMode, getActivationLevel, getConfigDir, getConfigPath, VALID_MODES, safeWriteFlag, readFlag, safeClearFlag, registryDefault };
