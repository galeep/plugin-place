---
name: caveman-stats
description: >
  Show real token usage and estimated savings for the current session.
  Reads directly from the Claude Code session log — no AI estimation.
  Triggers on /caveman-stats. Output is injected by the mode-tracker hook;
  the model itself does not compute the numbers.
---

When this skill fires (the user typed `/caveman-stats`), run the stats script and show its stdout to the user verbatim. Do not recompute or estimate the numbers yourself.

```bash
node "${CLAUDE_PLUGIN_ROOT}/src/hooks/caveman-stats.js"
```

The script reads the current Claude Code session log directly, auto-locating the most recent session under `~/.claude/projects/`, and prints real token usage plus an estimated savings figure from the benchmark. Optional flags: `--share` (shareable summary), `--all` (all sessions), `--since 7d` or `--since 24h` (limit the window).

Why the skill runs the script instead of relying on a hook: historically `caveman-mode-tracker.js` returned `decision: "block"` with the stats as the reason, but the harness drops that block-decision when `/caveman-stats` dispatches as a skill, so nothing renders. Running the script from the skill sidesteps that.
