---
name: caveman-stats
author: "Julius Brussee via galeep"
description: >
  Show real token usage and estimated savings for the current session, read
  from the session log. Trigger: /caveman-stats.
---

When this skill fires (the user typed `/caveman-stats`), run the stats script and show its stdout to the user verbatim. Do not recompute or estimate the numbers yourself.

```bash
node "${CLAUDE_PLUGIN_ROOT}/src/hooks/caveman-stats.js"
```

The script reads the current Claude Code session log directly, auto-locating the most recent session under `~/.claude/projects/`, and prints real token usage plus an estimated savings figure from the benchmark. Optional flags: `--share` (shareable summary), `--all` (all sessions), `--since 7d` or `--since 24h` (limit the window).

Why the skill runs the script instead of relying on a hook: historically `caveman-mode-tracker.js` returned `decision: "block"` with the stats as the reason, but the harness drops that block-decision when `/caveman-stats` dispatches as a skill, so nothing renders. Running the script from the skill sidesteps that.

Output also includes `Est. rule overhead` and `Est. net` lines wherever a savings estimate exists with a known turn count. Rule overhead is the estimated per-turn INPUT-token cost of the injected caveman rules (default 1,250 tokens/turn, override with `CAVEMAN_RULE_OVERHEAD_TOKENS`) times the turn count. Net is savings minus that overhead — when negative, the output says so plainly and suggests turning caveman off for that workload, rather than hiding the net-negative regime behind a gross-savings number (see `docs/HONEST-NUMBERS.md`).
