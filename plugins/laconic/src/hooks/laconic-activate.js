#!/usr/bin/env node
// laconic — Claude Code SessionStart hook.
//   1. Resolve the default register/level.
//   2. Write the active flag at $CLAUDE_CONFIG_DIR/.laconic-active.
//   3. Emit the register body (filtered to the active level) as SessionStart
//      context so the register anchors from turn one.

const path = require('path');
const os = require('os');
const { getDefaultMode, safeWriteFlag, safeClearFlag } = require('./laconic-config');
const registry = require('./laconic-registry');

// Filter a register body to a single level: drop OTHER levels' intensity-table
// rows and "- level:" example lines, keep everything else.
function filterToLevel(text, level) {
  return text.split('\n').reduce((acc, line) => {
    const row = line.match(/^\|\s*\*\*(\S+?)\*\*\s*\|/);
    if (row) { if (row[1] === level) acc.push(line); return acc; }
    const ex = line.match(/^- (\S+?):\s/);
    if (ex) { if (ex[1] === level) acc.push(line); return acc; }
    acc.push(line);
    return acc;
  }, []).join('\n');
}

const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const flagPath = path.join(claudeDir, '.laconic-active');

const mode = getDefaultMode();

// "off" — clear the flag, emit nothing substantive.
if (mode === 'off') {
  safeClearFlag(flagPath);
  process.stdout.write('OK');
  process.exit(0);
}

safeWriteFlag(flagPath, mode);

const reg = (() => { try { return registry.loadRegisters(); } catch (e) { return null; } })();
const resolved = reg ? registry.resolve(reg, mode) : null;

if (resolved) {
  const { register, token } = resolved;
  process.stdout.write(
    register.statusline + ' REGISTER ACTIVE — level: ' + token + '\n\n' +
    filterToLevel(register.body, token)
  );
} else {
  // Registry unresolvable (e.g. a bare hook install with no registers/ dir).
  // Minimal anchor so the register still applies.
  process.stdout.write(
    'LACONIC REGISTER ACTIVE — level: ' + mode + '\n\n' +
    'Telegraphic but literate: drop the function words a reader restores for free, ' +
    'keep the logic connectives, notebook symbols where they decode instantly. ' +
    'Full prose on high-value turns; compress only the final statement.'
  );
}
