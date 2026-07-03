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
//   3. the default register's default token (falls back to 'laconic')
//
// The flag I/O below is a clean-room implementation of the symlink-safe,
// size-capped, whitelist-validated pattern: refuse a symlink at the flag path
// or its parent (unless the parent resolves to a dir the current user owns),
// write atomically via temp+rename with O_NOFOLLOW and 0600, cap reads, and
// reject any value not on VALID_MODES. Prevents a local attacker from pointing
// the predictable flag path at a secret and having a reader slurp it into model
// context.

const fs = require('fs');
const path = require('path');
const os = require('os');
const registry = require('./laconic-registry');

const SPECIAL_MODES = ['off'];
const FALLBACK_DEFAULT = 'laconic';
const MAX_FLAG_BYTES = 64; // longest legit token is short; 64 leaves slack without enabling exfil

// Registry loaded once at module load. VALID_MODES = specials ∪ tokens ∪ aliases.
const REG = (() => { try { return registry.loadRegisters(); } catch (e) { return null; } })();

const VALID_MODES = (() => {
  const modes = SPECIAL_MODES.slice();
  if (REG) modes.push(...registry.allTokens(REG), ...registry.allAliases(REG));
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
    let st;
    try { st = fs.lstatSync(flagPath); } catch (e) { return null; }
    if (st.isSymbolicLink() || !st.isFile() || st.size > MAX_FLAG_BYTES) return null;

    const O_NOFOLLOW = typeof fs.constants.O_NOFOLLOW === 'number' ? fs.constants.O_NOFOLLOW : 0;
    let fd, out;
    try {
      fd = fs.openSync(flagPath, fs.constants.O_RDONLY | O_NOFOLLOW);
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

module.exports = { getDefaultMode, getConfigDir, getConfigPath, VALID_MODES, safeWriteFlag, readFlag, registryDefault };
