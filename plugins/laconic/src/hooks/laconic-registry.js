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

// Values a register's `default` field may hold that are NOT one of its own level
// tokens. 'off' means "do not activate unless asked", which is how a register
// ships opt-in: the SessionStart hook resolves the default, sees a special, and
// injects nothing. Declared here rather than in laconic-config.js because loadOne
// has to accept the value before config ever sees it; config derives its
// SPECIAL_MODES from this list so the whitelist cannot drift (the same reasoning
// that makes MAX_TOKEN_BYTES below the source for config's MAX_FLAG_BYTES).
// Registry cannot require config back: that is a cycle.
//
// What the derivation does NOT buy: the hooks treat any special as "do not
// activate" (they test membership in SPECIAL_MODES, not equality with 'off'), but
// nothing gives a second special its own distinct MEANING. Adding one makes it
// accepted, whitelisted, and behaviorally identical to 'off'. Implement it in the
// hooks before advertising it as different.
const SPECIAL_DEFAULTS = ['off'];

// Names no register may use for an id, a level token, or either side of an alias.
// Wider than SPECIAL_DEFAULTS, because reserving only the specials left a hole: the
// command surface also spells deactivation as `stop` and `disable`
// (laconic-mode-tracker.js), so a register declaring a level called `stop` produced a
// token that env, config and a bare activation would all accept while `/laconic stop`
// deactivated instead of selecting it. A name that cannot be asked for is not a
// usable level, so it is rejected at load.
const RESERVED_TOKENS = SPECIAL_DEFAULTS.concat(['stop', 'disable']);

// Ids, level tokens and aliases all go through this gate, so every RESERVED_TOKENS
// name is unusable as any of the three. Without that arm a register could declare a
// level literally named 'off': it would land in VALID_MODES, become the register's
// activationToken, and make an argument-less /laconic resolve to 'off' —
// deactivating on the command documented to activate, which is the failure the
// special-default handling exists to prevent. `stop` and `disable` are reserved for
// the same reason one step removed: they are how the command surface spells the same
// request.
function tokenOk(t) {
  return typeof t === 'string' && TOKEN_RE.test(t) && Buffer.byteLength(t, 'utf8') <= MAX_TOKEN_BYTES
    && !RESERVED_TOKENS.includes(t);
}

// Opt-in diagnostics. Every failure in this file is swallowed so a hook can never
// disrupt a session, which means a misconfigured register is indistinguishable
// from a healthy one at the surface. LACONIC_DEBUG=1 is the only channel that
// tells them apart, so each silent fallback that could be a defect writes here.
function debugOn() {
  return process.env.LACONIC_DEBUG === '1';
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

  if (debugOn() && json.default !== undefined
      && !tokens.includes(json.default) && !SPECIAL_DEFAULTS.includes(json.default)) {
    // A `default` that is neither a declared token nor a special is a typo, and
    // the fallback below quietly activates at tokens[0]: `"default": "of"` reads
    // as opt-in and behaves as opt-in-inverted. Nothing else surfaces it.
    process.stderr.write(`[laconic] registry: register '${json.id}' declares default '${json.default}', which is neither one of its tokens nor a special; using '${tokens[0]}'\n`);
  }
  if (debugOn() && json.default === undefined) {
    // Fires on a MISSING key as well as an absent one, which is the case a check on
    // the value cannot see: `"defualt": "off"` or `"Default": "off"` leaves
    // json.default undefined, so the register auto-activates at tokens[0] and the
    // opt-in request is inverted with nothing said. Not an error on its own, since
    // an omitted default is legal, so this is the one place it surfaces.
    process.stderr.write(`[laconic] registry: register '${json.id}' declares no 'default'; its session default is '${tokens[0]}' (check for a misspelled key if you meant it to be opt-in)\n`);
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
    // The level an argument-less activation resolves to WHEN THE SESSION DEFAULT
    // IS A SPECIAL. It is the last word, not the first: getActivationLevel()
    // returns the resolved session default whenever that is a level, so a
    // LACONIC_DEFAULT_MODE or a config.json defaultMode naming a level means this
    // field is never read. Separate from `default` because a register whose
    // session default is 'off' still needs a level to switch INTO once the user
    // actually asks. Prefers a real declared default, else the register's
    // eponymous token (the shape the README documents: id `myvoice` with tokens
    // myvoice-lite/myvoice/myvoice-ultra), else whichever token `tokens` lists
    // first, which is JSON key order and therefore the register author's problem
    // to get right.
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
  const debug = debugOn();
  // dirPresent distinguishes "this install ships no registers at all" (a bare
  // hook install, where a hardcoded default is the only useful answer) from
  // "registers/ is right there and every register in it was rejected" (a defect
  // in the data). Callers need the difference: treating the second as the first
  // makes a typo in register.json activate a register the data says is opt-in.
  const out = { registers: [], tokenMap: Object.create(null), aliasMap: Object.create(null), dirPresent: false };

  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (e) {
    // Only ENOENT means "this install ships no registers". Every other errno says
    // the path is there and unusable: EACCES for a dir we cannot read, ENOTDIR for
    // a file where a dir belongs. Treating those as absent sends callers down the
    // bare-install path, which resolves to a hardcoded level and overwrites a flag
    // the user set — a broken install that looks like a working one at a lower
    // level. Report the path as present so they can refuse instead.
    if (e.code !== 'ENOENT') {
      out.dirPresent = true;
      if (debug) process.stderr.write(`[laconic] registry: cannot read '${dir}' (${e.code}); no registers loaded\n`);
    }
    return out;
  }
  out.dirPresent = true;

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

module.exports = { loadRegisters, allTokens, allAliases, resolve, defaultRegistersDir, debugOn, MAX_TOKEN_BYTES, SPECIAL_DEFAULTS, RESERVED_TOKENS };
