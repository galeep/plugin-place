# Vendor `scientific-agents` and unify the grouping methodology

- **Date:** 2026-06-06
- **Status:** Approved (pending written-spec review)
- **Author:** galeep
- **Branch:** `feature/vendor-scientific-agents`

## Context

`plugin-place` already vendors K-Dense's `scientific-agent-skills` (≈140 tool/library
skills) and `claude-scientific-writer`, plus a downstream-patched `caveman`. The build
is driven by `plugins.yaml` (source of truth) through `scripts/render.py`, which copies
skills out of pinned submodules and generates `plugins/<name>/` trees and
`.claude-plugin/marketplace.json`.

K-Dense has since published a second, separate repository,
[`K-Dense-AI/scientific-agents`](https://github.com/K-Dense-AI/scientific-agents):
**503 expert "operating mind" profiles**, one scientific or engineering profession each.
We want these in the marketplace as installable plugins, grouped by domain, with
authorship attributed to the original author plus a "via galeep" vendor mark.

Two problems surfaced while scoping this:

1. **Format mismatch.** Each agent directory holds an `AGENTS.md` and a byte-identical
   `CLAUDE.md`, both plain prose with **no YAML frontmatter** (they open with
   `# AGENTS.md — Astrophysicist Agent`). These are AGENTS.md-standard project context
   files, not Claude Code subagents. K-Dense's own Claude Code instructions wire them as
   a project-root `CLAUDE.md → @AGENTS.md` import (a whole-session persona), not as
   delegatable subagents. Bundling therefore requires format conversion and frontmatter
   synthesis, not a file copy.

2. **Coverage drift.** `plugins.yaml` hand-lists every skill per plugin. The submodule
   is pinned at `v2.45.0` (141 skills) but the lists still reflect an older cut (135
   skills). Six skills are present upstream and bundled into no plugin: `autoskill`,
   `bids`, `exa-search`, `liteparse`, `nextflow`, `pacsomatic`. Hand-curation already
   leaked; 503 more items make it untenable.

`catalog.json` in the agents repo carries, per agent: `profession`, `slug`, `path`,
`work_mode`, `summary`, `created`, `updated`, `source_count`. Frontmatter synthesis and
classification can be driven mechanically from it.

## Goals

- Vendor all 503 agent profiles as **Claude Code subagents**, grouped into ~15
  domain plugins (no single plugin much over 50 subagents).
- Replace hand-maintained membership lists with a methodology that makes silent
  omission impossible, for both skills and agents.
- Attribute every vendored skill and agent in frontmatter as
  `author: "K-Dense, Inc. via galeep"`.
- Place the six orphaned skills.

## Non-goals (YAGNI)

- No skill-wrapped copies of the agents. Subagents only.
- No automatic bumping of the agents SHA pin.
- No new CI system; extend the existing drift check to the new submodule and assert
  the coverage gate passes.
- No reflowing of the existing skill plugins' editorial groupings or descriptions. The
  skills keep their current plugin shape; only their *membership mechanism* moves.

## Decisions

| Fork | Decision | Rationale |
|---|---|---|
| Agent target form | Claude Code subagents (`agents/<slug>.md`) | Most native to a plugin marketplace; delegatable via the Task/Agent tool. |
| Grouping | Domain-grouped, big buckets split (~15 plugins) | Discoverability; keeps any one plugin's subagent roster manageable. |
| Attribution shape | Single string `K-Dense, Inc. via galeep` | Avoids any risk from non-standard metadata keys; human-readable; safe in every tool. |
| Attribution scope | Skills **and** agents | "All the frontmatter." |
| Membership methodology | Hybrid: rules seed a committed, human-reviewed assignment table; build reads the table behind a coverage gate | Reviewable, fail-loud, nothing silently missed, and the rules do the grunt work. |
| Agents pin | By commit SHA (no tags exist) | `896ed6ed1e1a6686572db06ca59fd1c1b0055ca7` (2026-06-04). |
| Duplicate `CLAUDE.md` | Dropped | Byte-identical to `AGENTS.md`; one source. |

## Design

### A. New upstream

Add a submodule `vendor/scientific-agents` →
`https://github.com/K-Dense-AI/scientific-agents.git`, pinned at SHA
`896ed6ed1e1a6686572db06ca59fd1c1b0055ca7`. Add an `upstreams.scientific-agents` entry
to `plugins.yaml`. Because the repo has no tags, introduce a `pinned_sha` field;
`render.py` and `build.sh`'s submodule presence check accept `pinned_tag` **or**
`pinned_sha`. The provenance sidecar (`write_provenance_sidecar`) already records the
resolved SHA, so it works unchanged.

The agent profiles live under the repo's `scientific-agents/` subdirectory, so the
upstream entry records `agents_root: scientific-agents` and `catalog: catalog.json`.

### B. Membership methodology — one mechanism, two tables

`plugins.yaml` stops listing members. It retains plugin **metadata** only: `name`,
`kind`, `upstream`, `category`, `description`. Membership moves to committed tables:

| File | Role |
|---|---|
| `taxonomy/rules.yaml` | Ordered keyword→domain rules plus an `overrides:` map. **Read only by the seed generator**, never by the build. |
| `taxonomy/skills.yaml` | `<skill-slug>: <plugin-name>` for all 141 skills (migrated from the current inline lists, with the 6 orphans placed). |
| `taxonomy/agents.yaml` | `<agent-slug>: <plugin-name>` for all 503 agents. |

A new `scripts/seed_assignments.py`:

- Reads each submodule's actual contents (skill dirs; agent slugs from `catalog.json`).
- Applies `rules.yaml` (first match wins; `overrides` win over rules).
- Writes/updates the two tables, **preserving any existing human assignment** and
  appending newly-seen upstream items with the value `UNASSIGNED`.
- Is idempotent and safe to re-run after an upstream bump.

`render.py` gains a **coverage gate** run before any plugin is built:

- Every skill dir in the skills submodule must appear in `taxonomy/skills.yaml`.
- Every agent slug in `catalog.json` must appear in `taxonomy/agents.yaml`.
- No value may be `UNASSIGNED`, and every value must name a plugin that exists in
  `plugins.yaml`.
- Any violation aborts the build and lists the offending slugs.

This gate is the guarantee that no upstream item is ever silently dropped again.

Skill plugin membership is now derived: for a `built` plugin, its skill list is
"every skill whose `taxonomy/skills.yaml` value equals this plugin's name." The two
corpora keep **separate** tables because their natural groupings differ (skills are
tool-centric: `lab-automation`, `scientific-communication`; agents are
profession-centric: `volcanologist`, `civil-engineer`). One methodology, two inputs.
The existing skill plugins keep their current shape and descriptions; only the
membership mechanism moves from inline lists to the table.

### C. Agent → subagent conversion

For each agent slug assigned to plugin `P`:

- Source: `vendor/scientific-agents/scientific-agents/<slug>/AGENTS.md`
- Output: `plugins/P/agents/<slug>.md`
- Synthesized frontmatter (kept minimal):

  ```yaml
  ---
  name: <slug>
  description: "<Profession>: <catalog summary>"
  author: "K-Dense, Inc. via galeep"
  ---
  ```

  `name` is the catalog `slug`; `description` is `"{profession}: {summary}"` so the
  leading profession sharpens delegation triggering. The body is the `AGENTS.md`
  content kept **verbatim** (faithful provenance; keeps any future drift/patch
  detection meaningful).
- The duplicate `CLAUDE.md` is not copied.

A new `build_agents_plugin(plugin, upstream)` in `render.py` performs this, then writes
the plugin's `.claude-plugin/plugin.json` (author `K-Dense, Inc. via galeep`, homepage
the agents repo, license MIT) and a generated `README.md` listing the agents and the
provenance (repo + pinned SHA).

### D. Attribution retrofit for skills

Target string: `author: "K-Dense, Inc. via galeep"`.

Skill `SKILL.md` files already carry frontmatter such as `metadata.skill-author:
K-Dense Inc.`. Rather than parse and re-serialize the YAML (which risks mangling
multiline `description` blocks and reordering keys), inject at the **string level**:
after the first `---`, if no top-level `author:` line is present, insert
`author: "K-Dense, Inc. via galeep"` immediately after the `name:` line. The injection
is idempotent (skipped when an `author:` line already exists). The upstream
`metadata.skill-author` is left untouched as the original-author record; the new
top-level `author` is the vendor attribution.

### E. Agent plugins (~15, big buckets split)

Naming: `sci-agents-<domain>`. A draft keyword classification of all 503 produced these
buckets: clinical-medicine 93, life-sciences 91, engineering 78, earth-env-space 76,
physics-astro 60, agri-food-vet 26, cs-ai-data 26, math-stats-or 20, chemistry 18,
materials-nano 7 (8 stragglers needing one-line rules). Splitting the large buckets
to keep each plugin's roster manageable gives the seed layout below. **Exact split
boundaries are finalized during the table-review step**, not guessed here.

| Plugin | approx n | Source bucket |
|---|---|---|
| `sci-agents-clinical` | ~45 | clinical-medicine (split) |
| `sci-agents-medical-specialties` | ~48 | clinical-medicine (split) |
| `sci-agents-molecular-cell-biology` | ~46 | life-sciences (split) |
| `sci-agents-organismal-eco-biology` | ~45 | life-sciences (split) |
| `sci-agents-physics` | ~38 | physics-astro (split) |
| `sci-agents-astronomy-space` | ~30 | physics-astro + astro from earth-space |
| `sci-agents-earth-environment` | ~40 | earth-env-space (split) |
| `sci-agents-ocean-atmos-climate` | ~36 | earth-env-space (split) |
| `sci-agents-engineering` | ~45 | engineering (split) |
| `sci-agents-electrical-computer-hw` | ~33 | engineering (split) |
| `sci-agents-cs-ai-data` | ~26 | as-is |
| `sci-agents-agri-food-vet` | ~26 | as-is |
| `sci-agents-math-stats-or` | ~20 | as-is |
| `sci-agents-chemistry` | ~18 | as-is |
| `sci-agents-materials-nano` | ~7 | as-is |

### F. `render.py` changes (summary)

- Accept `pinned_sha` alongside `pinned_tag` wherever an upstream version is read.
- Load `taxonomy/skills.yaml` and `taxonomy/agents.yaml`; run the coverage gate.
- `built` skill plugins: derive `skills` from the skills table instead of an inline list.
- New `build_agents_plugin` for `kind: agents` plugins (the conversion in C).
- Attribution injector applied to every built skill `SKILL.md` (D) and used when
  synthesizing agent frontmatter (C).

## Implementation order

1. Add the `vendor/scientific-agents` submodule pinned at the SHA; add the upstream
   entry to `plugins.yaml`.
2. Author `taxonomy/rules.yaml` (seed rules + overrides for the 8 stragglers).
3. Write `scripts/seed_assignments.py`; generate `taxonomy/skills.yaml` and
   `taxonomy/agents.yaml`.
4. **Review the tables** — finalize the E split boundaries, confirm the 6 orphan skills
   land sensibly, spot-check agent assignments. Commit the locked tables.
5. Add the 15 agent plugin metadata entries to `plugins.yaml`; remove the inline skill
   lists.
6. Extend `render.py`: `pinned_sha`, table loading, coverage gate, `build_agents_plugin`,
   attribution injector, skill membership from table.
7. Run `scripts/build.sh`; run `scripts/validate-plugin.sh` across all plugins.
8. Extend the CI drift check to the new submodule; assert the coverage gate.
9. Open a PR.

## Risks and mitigations

- **Heuristic misclassification.** Mitigated by the human-reviewed, committed table
  (step 4) and the `overrides` map; the build never reclassifies on its own.
- **Subagent delegation noise.** 503 auto-delegating descriptions could over-trigger.
  Mitigated by per-domain plugins (users install only their field) and by the
  `"{profession}: …"` description prefix that scopes each agent.
- **Frontmatter injection corrupting a skill.** Mitigated by string-level idempotent
  insertion (no YAML round-trip) and by `validate-plugin.sh` over the built tree.
- **Upstream bump reintroducing drift.** Mitigated by the coverage gate: new items
  appear as `UNASSIGNED` and fail the build until placed.

## Provenance and attribution

- Agents: vendored from `K-Dense-AI/scientific-agents` @ `896ed6e`, MIT, © K-Dense, Inc.
- Every vendored skill and agent carries `author: "K-Dense, Inc. via galeep"` in
  frontmatter; skills additionally retain upstream `metadata.skill-author`.
- Per-plugin `README.md` and `plugin.json` record the upstream repo, license, and pin.
