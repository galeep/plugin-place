<p align="center">
  <img src="docs/plugin-place-sign.svg" alt="Plugin Place" width="640">
</p>

# plugin-place

A personal, curated [Claude Code](https://docs.claude.com/en/docs/claude-code)
plugin marketplace. It vendors a handful of upstream skill and agent collections
at pinned versions, then groups them into focused plugins you can install one at
a time. A few get a small downstream tweak, short of a fork.

## Why this exists

Many of the upstream collections this draws on ship as bare skills and agent
profiles, with no marketplace wrapper to install or update them as a unit.
Managing loose skills by hand (copying directories around, re-checking what
changed on each release) is tedious and easy to get wrong. This is the wrapper I
wanted: it vendors those collections at pinned versions and regenerates
everything from a single manifest, so installing a whole domain is one command.
Some already ship as plugins; those are vendored close to intact, with a small
downstream adjustment where I wanted to change a behavior without forking the
whole thing.

It also tries to be careful about provenance. Skills in particular get passed
around like plain text files, copied from repo to repo with `cp` until the
original author and version fall off. Plugins hold up better, since the format
ships a manifest naming an author and a source; a loose skill is just a markdown
file with nothing to keep the credit attached. I would rather not add to that
pile, so each piece here keeps its origin: every vendored skill and agent carries
the author and license its upstream provides. Partly that is principle and partly
it is laziness, since vendoring with a record is less work than keeping a fork.

It is a personal toolkit kept in the open, since the friction behind it is not
mine alone. If you hit the same rough edges, you are welcome to use it.

## Quick start

```sh
# Add the marketplace (one time)
claude plugin marketplace add galeep/plugin-place

# Browse the current, authoritative list of plugins
claude plugin search @plugin-place

# Install whichever pieces you want
claude plugin install sci-bioinformatics-genomics@plugin-place
claude plugin install sci-agents-chemistry@plugin-place
```

The live inventory lives in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)
and in `claude plugin search`. This README deliberately does not list plugin
counts or per-plugin rosters: those are generated from `plugins.yaml` and would
fall out of date the moment an upstream changed. Check the marketplace for what
is actually there right now.

## What's inside

Four upstreams are vendored as pinned git submodules. The exact pinned versions
live in [`plugins.yaml`](plugins.yaml) and [`.claude-plugin/provenance.json`](.claude-plugin/provenance.json),
so they are recorded in exactly one place rather than copied into prose here.

- **[K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills)**:
  scientific tool and library skills, split into domain plugins named
  `sci-<domain>` (for example `sci-bioinformatics-genomics`,
  `sci-machine-learning`), plus general-purpose document tools in
  `kdense-document-skills`.
- **[K-Dense-AI/scientific-agents](https://github.com/K-Dense-AI/scientific-agents)**:
  expert "operating mind" profiles, converted into Claude Code subagents and
  grouped by domain as `sci-agents-<domain>` (for example `sci-agents-chemistry`,
  `sci-agents-clinical`). Each subagent reasons in the voice of a senior
  practitioner in its field.
- **[K-Dense-AI/claude-scientific-writer](https://github.com/K-Dense-AI/claude-scientific-writer)**:
  the full writer plugin, including its `/scientific-writer-init` command,
  vendored intact as `claude-scientific-writer`.
- **[JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman)**:
  a compressed-communication mode, vendored as `caveman` with a small
  downstream patch (see [How it's built](#how-its-built)).

Naming convention: skill plugins are `sci-<domain>`, agent plugins are
`sci-agents-<domain>`, and the two standalone plugins keep their upstream names.
For the full current set, query the marketplace.

## Overlap: writer vs. sci-* plugins

`claude-scientific-writer` and the `sci-*` skill plugins share most of their
skills, because K-Dense maintains the same skill code in both upstreams. The
writer's unique contribution is the `/scientific-writer-init` command.

Pick one approach:

- **Install the writer** for the full writing and clinical skill set plus the
  init command, in a single plugin.
- **Install individual `sci-*` plugins** for exactly the domain slices you want,
  with granular enable and disable.

Installing both produces duplicate skill names, which Claude Code's skill router
does not handle well. Choose one.

## How it's built

[`plugins.yaml`](plugins.yaml) is the source of truth. Everything under
`plugins/`, the per-plugin manifests, and `.claude-plugin/marketplace.json` are
generated:

```sh
git submodule update --init --recursive
bash scripts/build.sh
```

The build is idempotent. Edits inside `plugins/` are overwritten on the next run,
so changes belong in `plugins.yaml`, the `taxonomy/` tables, or `patches/`.

Plugin kinds:

- **built**: copies a chosen set of skills from an upstream submodule into a
  domain plugin.
- **agents**: converts upstream `AGENTS.md` profiles into Claude Code subagents.
- **vendored**: copies an entire upstream plugin intact (skills, commands,
  agents, hooks).
- **vendored-whole**: like `vendored`, but preserves the upstream's own
  `plugin.json` so its hooks and wiring survive (used for `caveman`).

A few properties the build enforces:

- **Coverage gate.** Membership for skills and agents is recorded in committed
  assignment tables under [`taxonomy/`](taxonomy/). The build fails if any
  upstream skill or agent is unassigned, mapped to a plugin that does not exist,
  or left as a stale entry. Nothing is silently dropped.
- **Attribution.** Every vendored skill and agent carries an `author` line in
  its frontmatter crediting the original author with a `via galeep` vendor mark
  (for example `author: "K-Dense Inc. via galeep"`). Unknown origins are never
  fabricated.
- **Per-skill licenses.** Each skill's real license is carried through; a
  plugin's license is the single value when its skills agree, or
  `mixed (see individual skills)` otherwise, with per-skill licenses listed in
  the plugin README.
- **Downstream patches.** Edits to vendored content live in [`patches/`](patches/)
  as exact find-and-replace anchors applied on every build. A patch whose anchor
  no longer matches fails the build, so upstream drift is surfaced rather than
  silently absorbed.

To add or change a plugin, edit `plugins.yaml` (and the `taxonomy/` tables for
membership), then rerun `scripts/build.sh`.

## Staying in sync with upstream

A daily GitHub Actions workflow checks each tag-pinned upstream for a newer
release. When it finds one, it bumps the submodule, rebuilds, and opens a pull
request for review. SHA-pinned upstreams (the ones without release tags) are
bumped manually.

Manual sync for a SHA-pinned upstream:

```sh
cd vendor/<submodule> && git fetch && git checkout <sha>
cd ../.. && bash scripts/build.sh
# then update the pin in plugins.yaml
```

## Attribution and license

The plugins distributed here are derivative works of their upstreams' content,
vendored under the upstreams' own licenses. Each `vendor/*/` submodule preserves
the upstream `LICENSE`, and every vendored skill and agent records its original
author in its frontmatter, which is the authoritative credit record.

All credit for the underlying skills and agents goes to their original authors,
and they are many. Beyond the upstream organizations, the corpus includes work
by independent authors and labs such as Harvard MIMS (PrimeKG), Exa, and many
individual contributors. This repository is only the packaging: the vendoring,
taxonomy, and marketplace wrapper. Authorship is entirely upstream.

This repository's own scaffolding (build scripts, manifest, taxonomy, docs) is
MIT-licensed; see [`LICENSE`](LICENSE).
