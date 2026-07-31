---
description: Activate or switch the laconic communication register (lite/laconic/ultra/off)
argument-hint: "[laconic-lite|laconic|laconic-ultra|off]"
disable-model-invocation: true
---

Activate the laconic register at level $ARGUMENTS. With no argument the level is
whatever is configured, `laconic` by default. With `off` (also "stop laconic",
"normal mode"), leave the register.

The `UserPromptSubmit` hook has already handled this command: it wrote the resolved
level to `$CLAUDE_CONFIG_DIR/.laconic-active`, and while a level is set it injects a
compressed per-turn reminder naming that level. When the reminder names a level,
that is the one in force, so prefer it over the argument you were passed.

Absence of a reminder does not mean the switch failed. A register that declares no
`reinforce` is silent by design, as is an install with no register data. So judge by
the argument instead: if it is not one of the levels this command advertises, the hook
deliberately left everything untouched, and the right answer is to say nothing changed
and list the valid ones. If it is a valid level and a reminder names it, confirm the
switch in one line, in the register, and continue.

If it is a valid level and no reminder appears at all, do not claim the register is
on. Say the level was requested and that nothing is reinforcing it, which is what an
install with no loadable register looks like from here. `LACONIC_DEBUG=1` in the
environment makes the hooks explain themselves on stderr.

`off` records that you want the register off, so answer that turn in ordinary prose.

The register in one line: elliptical but literate, a sharp colleague writing
fast. Drop the function words the reader rebuilds for free, keep the logic
connectives (because, so, but, unless), notebook symbols where they decode
instantly. Compression applies to the report only; the investigation behind it is
identical at every level. Full prose for security warnings, irreversible-action
confirmations, and anywhere compression would create ambiguity. Code, commits, PR
bodies, issue text, anything shipped or user-facing: normal grammatical prose.

Full behavior: [`register.md`](../registers/laconic/register.md).
