# laconic

A value-proportional communication **register engine** for Claude Code. Ships
one register, `laconic`: elliptical but literate, the way a sharp colleague
writes when busy. Drop the function words a reader restores for free, keep the
logic connectives, use notebook symbols where they decode instantly. Full prose
on high-value turns; compress only the final statement.

It compresses the **report**, never the work behind it. Files read, checks
actually run, claims verified, and scope finished are identical at every level,
so `laconic-ultra` means denser output, not less effort.

Unlike a single-voice style plugin, laconic is **data-driven**: a register is a
pair of files, so adding a new voice needs no code change.

## Usage

```
/laconic                 # activate at the default level (laconic)
/laconic laconic-lite    # articles + full grammar, just cut the filler
/laconic laconic-ultra   # max symbol density, grammar held where logic needs it
/laconic off             # deactivate (also: "stop laconic", "normal mode")
```

Set a session default without typing a command:

- env: `LACONIC_DEFAULT_MODE=laconic-lite`
- config: `~/.config/laconic/config.json` → `{ "defaultMode": "laconic" }`

## How it works

Two hooks, wired in `.claude-plugin/plugin.json`:

- **SessionStart** (`src/hooks/laconic-activate.js`) writes the active-register
  flag at `$CLAUDE_CONFIG_DIR/.laconic-active` and injects the register body,
  filtered to the active level, so the register anchors from turn one.
- **UserPromptSubmit** (`src/hooks/laconic-mode-tracker.js`) handles `/laconic`
  commands and re-injects a compressed per-turn reminder, so the register
  survives context compaction and other plugins' competing style injections.

Flag I/O (`src/hooks/laconic-config.js`) is symlink-safe, size-capped, and
whitelist-validated: a flag that is missing, oversized, or a symlink pointing at
a secret yields nothing rather than leaking bytes into model context.

## Adding a register

A register is a directory under `registers/<id>/`:

- `register.json` — machine fields:
  ```json
  {
    "id": "myvoice",
    "default": "myvoice",
    "statusline": "MYVOICE",
    "aliases": { "shorthand": "myvoice" },
    "tokens": { "myvoice-lite": "...", "myvoice": "...", "myvoice-ultra": "..." },
    "reinforce": "MYVOICE ACTIVE ({token}). <per-turn reminder text>"
  }
  ```
- `register.md` — the SessionStart body: opener, rules, an **Intensity** table
  whose rows are keyed `| **<token>** | ... |`, and per-level examples keyed
  `- <token>: ...`. The activate hook filters both to the active level.

Drop the directory in. `laconic-config.js` derives `VALID_MODES` from the
registry at load, so the new tokens are valid immediately. No list to update, no
code to touch. Token collisions resolve first-by-sorted **directory name** (not
by the `id` field, which may differ from the directory it lives in); set
`LACONIC_DEBUG=1` to see skipped/collided registers on stderr.

## Layout

```
plugins/laconic/
  .claude-plugin/plugin.json      # hook wiring
  registers/laconic/
    register.json                 # machine fields
    register.md                   # register body (source of truth)
  skills/laconic/SKILL.md         # /laconic command + doc
  src/hooks/
    laconic-registry.js           # data-driven register loader
    laconic-config.js             # flag I/O + VALID_MODES + default resolution
    laconic-activate.js           # SessionStart
    laconic-mode-tracker.js       # UserPromptSubmit
```

Declared `kind: local` in `plugins.yaml`, so `render.py` treats these files as
source of truth and never regenerates them.
