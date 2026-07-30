#!/usr/bin/env node
// laconic — register registry
//
// A "register" is a named communication voice defined as DATA, not code:
// a directory under <plugin_root>/registers/<id>/ holding
//   register.json — machine fields { id, default, statusline, aliases, tokens, reinforce }
//   register.md   — the SessionStart body (opener, rules, intensity table, boundaries)
//
// Adding a new register = drop a new dir. No code change. The hooks (activate,
// mode-tracker, config) resolve an active mode-token to its owning register via
// this module.
//
// Fail-safe by construction: any unreadable/invalid register is skipped, never
// throws. If the registers dir is absent entirely, loadRegisters returns an
// empty registry and callers fall back to their hardcoded defaults.

const fs = require('fs');
const path = require('path');

// Resolve <plugin_root>/registers from this file at <plugin_root>/src/hooks/.
function defaultRegistersDir() {
  return path.join(__dirname, '..', '..', 'registers');
}

// Token/id sanity: lowercase alnum + single dashes. Rejects path traversal,
// whitespace, and anything that could not be a legitimate flag value.
const TOKEN_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

// Upper bound on a token's on-disk size. The flag file is read back with a hard
// cap, so a token longer than this could be WRITTEN and then never READ: the
// hooks would persist a mode the reader always rejects, and activation would
// silently no-op. Bounding at load keeps VALID_MODES incapable of holding a
// token that cannot round-trip. laconic-config.js derives its MAX_FLAG_BYTES
// from this constant so the two cannot drift apart.
const MAX_TOKEN_BYTES = 64;

// Values a register's `default` field may hold that are NOT one of its own
// level tokens. 'off' means "do not activate unless asked", which is how a
// register ships opt-in: the SessionStart hook resolves the default, sees 'off',
// and injects nothing. Declared here rather than in laconic-config.js because
// loadOne has to accept the value before config ever sees it; config derives its
// SPECIAL_MODES from this list so the two cannot drift (same reasoning as
// MAX_FLAG_BYTES above). Registry cannot require config back: that is a cycle.
const SPECIAL_DEFAULTS = ['off'];

function tokenOk(t) {
  return typeof t === 'string' && TOKEN_RE.test(t) && Buffer.byteLength(t, 'utf8') <= MAX_TOKEN_BYTES;
}

function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

// Load one register dir. Returns a normalized register object or null on any
// defect (missing/invalid json, missing body, bad tokens). Never throws.
function loadOne(dir) {
  let json;
  try {
    json = JSON.parse(fs.readFileSync(path.join(dir, 'register.json'), 'utf8'));
  } catch (e) {
    return null;
  }
  if (!isPlainObject(json) || !tokenOk(json.id)) {
    return null;
  }
  if (!isPlainObject(json.tokens)) return null;

  const tokens = Object.keys(json.tokens).filter(tokenOk);
  if (tokens.length === 0) return null;

  let body = '';
  try {
    body = fs.readFileSync(path.join(dir, 'register.md'), 'utf8');
  } catch (e) {
    return null; // a register with no body is unusable
  }

  const aliases = {};
  if (isPlainObject(json.aliases)) {
    for (const [from, to] of Object.entries(json.aliases)) {
      // Alias must map to a real token this register owns.
      if (tokenOk(from) && tokenOk(to) && tokens.includes(to)) {
        aliases[from] = to;
      }
    }
  }

  return {
    id: json.id,
    dir,
    // The session default. May be a level token or a special ('off'). Without
    // the SPECIAL_DEFAULTS arm, `"default": "off"` fell through to tokens[0] and
    // the register activated at whatever level happened to be declared first:
    // the opt-in request was accepted, written to disk, and silently inverted.
    default: (tokens.includes(json.default) || SPECIAL_DEFAULTS.includes(json.default))
      ? json.default
      : tokens[0],
    // The level an explicit, argument-less activation resolves to. Separate from
    // `default` because a register whose session default is 'off' still needs a
    // level to switch INTO when the user actually asks for it. Prefers a real
    // declared default, else the register's eponymous token (the shape the README
    // documents: id `myvoice` with tokens myvoice-lite/myvoice/myvoice-ultra),
    // else the first token.
    activationToken: tokens.includes(json.default)
      ? json.default
      : tokens.includes(json.id) ? json.id : tokens[0],
    statusline: typeof json.statusline === 'string' ? json.statusline : json.id.toUpperCase(),
    tokens,
    aliases,
    reinforce: typeof json.reinforce === 'string' ? json.reinforce : '',
    body,
  };
}

// Scan the registers dir. Deterministic order (sorted by dir name) so token-
// collision resolution and any listing is stable across runs. On collision
// (two registers claim the same token or alias), first-by-sorted-name wins and
// the loser's colliding token is dropped — logged under LACONIC_DEBUG=1.
function loadRegisters(baseDir) {
  const dir = baseDir || defaultRegistersDir();
  const debug = process.env.LACONIC_DEBUG === '1';
  const out = { registers: [], tokenMap: Object.create(null), aliasMap: Object.create(null) };

  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (e) {
    return out; // no registers dir — empty registry, callers fall back
  }

  const dirs = entries
    .filter(e => e.isDirectory())
    .map(e => e.name)
    .sort();

  for (const name of dirs) {
    const reg = loadOne(path.join(dir, name));
    if (!reg) {
      if (debug) process.stderr.write(`[laconic] registry: skipped invalid register '${name}'\n`);
      continue;
    }
    out.registers.push(reg);
    for (const t of reg.tokens) {
      if (out.tokenMap[t]) {
        if (debug) process.stderr.write(`[laconic] registry: token '${t}' already owned by '${out.tokenMap[t].id}', ignoring '${reg.id}' claim\n`);
        continue;
      }
      out.tokenMap[t] = reg;
    }
    for (const [from, to] of Object.entries(reg.aliases)) {
      if (out.tokenMap[from] || out.aliasMap[from]) continue; // never shadow a real token
      // The alias target must be a token THIS register actually won. Without
      // this check an alias resurrects a token that lost a collision: loadOne
      // only proved `to` is declared by the register, not that the register
      // still owns it after cross-register collision resolution. Registering it
      // anyway would make the dropped token reachable through the back door and
      // contradict first-by-sorted-name resolution.
      if (out.tokenMap[to] !== reg) {
        if (debug) process.stderr.write(`[laconic] registry: alias '${from}' -> '${to}' dropped; '${reg.id}' does not own that token after collision resolution\n`);
        continue;
      }
      out.aliasMap[from] = { register: reg, token: to };
    }
  }
  return out;
}

// All canonical (non-alias) tokens across every register.
function allTokens(registry) {
  return Object.keys(registry.tokenMap);
}

// All aliases across every register.
function allAliases(registry) {
  return Object.keys(registry.aliasMap);
}

// Resolve a mode string (canonical token or alias) to { register, token }.
// Returns null if unknown.
function resolve(registry, mode) {
  if (typeof mode !== 'string') return null;
  const m = mode.toLowerCase();
  if (registry.tokenMap[m]) return { register: registry.tokenMap[m], token: m };
  if (registry.aliasMap[m]) return { register: registry.aliasMap[m].register, token: registry.aliasMap[m].token };
  return null;
}

module.exports = { loadRegisters, allTokens, allAliases, resolve, defaultRegistersDir, MAX_TOKEN_BYTES, SPECIAL_DEFAULTS };
