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

Activation is opt-in. The shipped register declares `"default": "off"`, so
installing the plugin costs nothing until you ask for the register: a fresh
install injects nothing at SessionStart and emits no per-turn reminder. Once you
activate a level it holds, including across later sessions, because the active
level lives in a flag file rather than in the session. `/laconic off` is what
turns it back off.

```
/laconic                 # activate at the register's own level (laconic)
/laconic laconic-lite    # articles + full grammar, just cut the filler
/laconic laconic-ultra   # max symbol density, grammar held where logic needs it
/laconic off             # deactivate (also: "stop laconic", "normal mode")
```

Set a session default without typing a command:

- env: `LACONIC_DEFAULT_MODE=laconic-lite`
- config: `~/.config/laconic/config.json` → `{ "defaultMode": "laconic" }`

Either one seeds a session that has no level active yet. Neither overrides a level
you switched to with `/laconic`, because SessionStart runs again on every resume and
compaction and a default that outranked your choice would undo it mid-session. Set
either to `off` to override in the other direction: that is a kill switch, and it
clears an active level.

## How it works

Two hooks, wired in `.claude-plugin/plugin.json`:

- **SessionStart** (`src/hooks/laconic-activate.js`) decides what is active. A level
  recorded in the flag at `$CLAUDE_CONFIG_DIR/.laconic-active` wins: it injects that
  level's body, filtered, and writes nothing. A recorded `off` also wins, and injects
  nothing. With no flag at all it applies the session default, writing the flag if
  that default is a level. An `off` set explicitly by env var or config file overrides
  even a recorded level, because that is a kill switch. A flag that exists but cannot
  be read is left untouched and nothing is injected. SessionStart fires on resume,
  clear and compact as well as startup, which is why it defers to the flag rather than
  reasserting a default over it.
- **UserPromptSubmit** (`src/hooks/laconic-mode-tracker.js`) handles `/laconic`
  commands and re-injects a compressed per-turn reminder, so the register
  survives context compaction and other plugins' competing style injections.

Flag I/O (`src/hooks/laconic-config.js`) is size-capped and whitelist-validated, and
refuses a symlink at the flag path: a flag that is missing, oversized, or a symlink
pointing at a secret yields nothing rather than leaking bytes into model context. What
it reliably buys is that last part, since the read is validated against the whitelist
before it is returned, so even a fully successful attack yields a known short token.

The symlink handling is narrower than "symlink-safe" would suggest, and the file says
so in its own header: only the flag's immediate parent is examined, so a symlinked
ancestor above it is not detected; the ownership check applies only on the symlink
branch, so a plain world-writable parent passes; and Windows has neither `O_NOFOLLOW`
nor a uid check. Tracked in #55.

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
  `default` is the session default: a level token, or `off` to ship the register
  opt-in. When it is `off`, an argument-less `/laconic` activates the token named
  after the register's `id` (`myvoice` above), falling back to whichever token
  `tokens` lists first. That resolution reads one register only: the one whose
  `id` is `laconic`, or the alphabetically first directory if no register claims
  that id. So a second register alongside the shipped one is reachable by name
  (`/laconic myvoice`) but does not get a say in what a bare `/laconic` does.
  An explicit level, from `LACONIC_DEFAULT_MODE` or the config file, outranks this
  field entirely.
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
  commands/laconic.md             # /laconic [level|off]
  registers/laconic/
    register.json                 # machine fields
    register.md                   # register body (source of truth)
  skills/laconic/SKILL.md         # register doc + summary
  src/hooks/
    laconic-registry.js           # data-driven register loader
    laconic-config.js             # flag I/O + VALID_MODES + default resolution
    laconic-activate.js           # SessionStart
    laconic-mode-tracker.js       # UserPromptSubmit
```

Declared `kind: local` in `plugins.yaml`, so `render.py` treats these files as
source of truth and never regenerates them.
