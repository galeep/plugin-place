#!/usr/bin/env node
// laconic — Claude Code UserPromptSubmit hook.
//   1. Handle /laconic [level|off] commands + "stop laconic" / "normal mode".
//   2. Emit the active register's per-turn reinforcement so the register stays
//      in the model's attention every turn (survives compaction, resists other
//      plugins' competing style injections).

const fs = require('fs');
const path = require('path');
const os = require('os');
const { getDefaultMode, safeWriteFlag, readFlag, VALID_MODES } = require('./laconic-config');
const registry = require('./laconic-registry');

const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const flagPath = path.join(claudeDir, '.laconic-active');

let input = '';
process.stdin.on('data', chunk => { input += chunk; });
// Broken pipe / parent crash emits 'error'; without a listener Node throws it
// uncaught and the hook exits non-zero. Hooks must always exit 0.
process.stdin.on('error', () => process.exit(0));
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    const prompt = (data.prompt || '').trim().toLowerCase().replace(/\s+/g, ' ');

    // Deactivation intent, computed first so "turn laconic off" never falls
    // through to activation.
    const wantsOff =
      /\b(stop|disable|deactivate|turn off)\s+(the\s+)?laconic\b/.test(prompt) ||
      /\blaconic\s+(off|stop|disabled?)\b/.test(prompt) ||
      /^(please\s+)?(go\s+|back\s+to\s+|switch\s+(back\s+)?to\s+|return\s+to\s+)?normal\s+mode\b/.test(prompt);

    // /laconic [level|off] — explicit switch.
    if (prompt.startsWith('/laconic')) {
      const arg = prompt.split(' ')[1] || '';
      let mode = null;
      if (!arg) mode = getDefaultMode();
      else if (arg === 'off' || arg === 'stop' || arg === 'disable') mode = 'off';
      else if (VALID_MODES.includes(arg)) mode = arg;
      // Unknown arg leaves the flag untouched (no silent overwrite).
      if (mode === 'off') { try { fs.unlinkSync(flagPath); } catch (e) {} }
      else if (mode) safeWriteFlag(flagPath, mode);
    } else if (wantsOff) {
      try { fs.unlinkSync(flagPath); } catch (e) {}
    }

    // Per-turn reinforcement from the active register. readFlag enforces
    // symlink-safe read + size cap + VALID_MODES whitelist, so a missing,
    // corrupted, oversized, or symlinked flag yields null and we emit nothing.
    const activeMode = readFlag(flagPath);
    if (activeMode) {
      let reinforce = null;
      try {
        const reg = registry.loadRegisters();
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
