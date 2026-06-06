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

2. **Coverage drift, two layers.** `plugins.yaml` hand-lists every skill per plugin.
   The submodule is pinned at `v2.45.0` (141 skills) but the lists still reflect an
   older cut (135 skills): six skills are present upstream and bundled into no plugin
   (`autoskill`, `bids`, `exa-search`, `liteparse`, `nextflow`, `pacsomatic`).
   Separately, the **pin itself is stale**: upstream `main` is 8 commits past `v2.45.0`,
   adding 2 new skills (`bulk-rnaseq`, `pathway-enrichment`) and content updates to 7
   existing ones, with no newer tag cut. Re-pinning to `main` (see Decisions) plus the
   existing gap means 8 orphan skills to place. Hand-curation already leaked; 503 more
   agent items make it untenable.

3. **Heterogeneous authorship and licensing in the skills corpus.** The 141 skills carry
   13 distinct `metadata.skill-author` values (114 are K-Dense Inc.; the rest are
   third parties such as Yaroslav Halchenko or Anthropic's document skills) and 8 carry
   none. Their licenses span MIT, BSD, Apache, GPL-2/3, CC-BY-4.0, CeCILL, proprietary,
   and unknown. The current build flattens both: it adds no vendor attribution and
   stamps every plugin `MIT` from the upstream blanket. The agents corpus, by contrast,
   is uniformly K-Dense / MIT.

`catalog.json` in the agents repo carries, per agent: `profession`, `slug`, `path`,
`work_mode`, `summary`, `created`, `updated`, `source_count`. Frontmatter synthesis and
classification can be driven mechanically from it.

## Goals

- Vendor all 503 agent profiles as **Claude Code subagents**, grouped into ~15
  domain plugins (no single plugin much over 50 subagents).
- Replace hand-maintained membership lists with a methodology that makes silent
  omission impossible, for both skills and agents.
- Attribute every vendored skill and agent in frontmatter with a "via galeep" vendor
  mark over the correct original author (per-skill for skills; a single string for
  agents).
- Re-pin the skills submodule to current upstream and place all resulting orphan
  skills (the 6 existing plus the 2 newly added: `bulk-rnaseq`, `pathway-enrichment`).
- Carry each skill's real license through to plugin metadata.

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
| Attribution (agents) | Single string `author: "K-Dense, Inc. via galeep"` | Agents are uniformly K-Dense/MIT with no per-file author; one string is correct. |
| Attribution (skills) | Per-skill derived `author: "{skill-author} via galeep"`; the 8 skills with no `skill-author` get `author: "via galeep"` | Skills have 13 distinct original authors; a flat string would misattribute 19 of them, and unknown origins must not be fabricated. |
| Attribution scope | Skills **and** agents | "All the frontmatter." |
| Membership methodology | Hybrid: rules seed a committed, human-reviewed assignment table; build reads the table behind a coverage gate | Reviewable, fail-loud, nothing silently missed, and the rules do the grunt work. |
| Skills pin | Re-pinned to main HEAD by SHA `b2a969eb56d92c454e682138cd93587d77b64b11` (2026-06-04) | The `v2.45.0` tag was 8 commits behind: missing 2 new skills + 7 content updates. No newer tag exists. |
| Agents pin | By commit SHA (no tags exist) | `896ed6ed1e1a6686572db06ca59fd1c1b0055ca7` (2026-06-04). |
| Per-skill license | Carry each skill's real license into output; a plugin's license is the single normalized license if uniform, else `mixed (see individual skills)` | The current build mis-stamps `MIT` on plugins that contain GPL/CC/proprietary skills. |
| Duplicate `CLAUDE.md` | Dropped | Byte-identical to `AGENTS.md`; one source. |

## Design

### A. Upstreams

**New — agents.** Add a submodule `vendor/scientific-agents` →
`https://github.com/K-Dense-AI/scientific-agents.git`, pinned at SHA
`896ed6ed1e1a6686572db06ca59fd1c1b0055ca7`. Add an `upstreams.scientific-agents` entry
to `plugins.yaml`. The agent profiles live under the repo's `scientific-agents/`
subdirectory, so the entry records `agents_root: scientific-agents` and
`catalog: catalog.json`.

**Bumped — skills.** Re-pin `vendor/scientific-agent-skills` from `v2.45.0` to main
HEAD `b2a969eb56d92c454e682138cd93587d77b64b11`. This picks up the 2 new skills and 7
content updates.

Because neither pin is a tag, introduce a `pinned_sha` field; `render.py` and
`build.sh`'s submodule presence check accept `pinned_tag` **or** `pinned_sha`. The
provenance sidecar (`write_provenance_sidecar`) already records the resolved SHA, so it
works unchanged. The `upstreams.*.license` field becomes a fallback only; the real
per-skill license (Section D2) takes precedence in generated metadata.

### B. Membership methodology — one mechanism, two tables

`plugins.yaml` stops listing members. It retains plugin **metadata** only: `name`,
`kind`, `upstream`, `category`, `description`. Membership moves to committed tables:

| File | Role |
|---|---|
| `taxonomy/rules.yaml` | Ordered keyword→domain rules plus an `overrides:` map. **Read only by the seed generator**, never by the build. |
| `taxonomy/skills.yaml` | `<skill-slug>: <plugin-name>` for every skill (migrated from the current inline lists, with the 8 orphan/new skills placed). |
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

**Proposed homes for the 8 orphan/new skills** (seed values for the table; confirmed at
review):

| Skill | Proposed plugin | Why |
|---|---|---|
| `bulk-rnaseq` | `sci-bioinformatics-genomics` | RNA-seq workflow |
| `pathway-enrichment` | `sci-bioinformatics-genomics` | enrichment analysis |
| `nextflow` | `sci-bioinformatics-genomics` | nf-core pipeline engine |
| `pacsomatic` | `sci-bioinformatics-genomics` | nf-core tumor/normal somatic pipeline |
| `bids` | `sci-medical-imaging` | Brain Imaging Data Structure (neuroimaging) |
| `exa-search` | `sci-scientific-communication` | scholarly web search, peer of `parallel-web` |
| `liteparse` | `sci-scientific-communication` | document/PDF parsing, peer of `markitdown` |
| `autoskill` | `sci-research-methodology` | meta/skill-authoring (cognitive/meta tools) |

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

### D1. Attribution retrofit

The vendor mark is `via galeep`, layered over the correct original author.

**Skills — per-skill derived.** The original author is each skill's existing
`metadata.skill-author`. The injected value is:

- `author: "{skill-author} via galeep"` when `skill-author` is present
  (e.g. `"K-Dense Inc. via galeep"`, `"Yaroslav Halchenko via galeep"`).
- `author: "via galeep"` for the 8 skills with no `skill-author` (vendor mark only; the
  true origin — e.g. Anthropic for `docx`/`pdf`/`pptx` — is not fabricated).

Rather than parse and re-serialize the YAML (which risks mangling multiline
`description` blocks and reordering keys), inject at the **string level**: read the
existing `skill-author` from the frontmatter, then, if no top-level `author:` line is
present, insert the computed `author:` line immediately after the `name:` line. The
injection is idempotent (skipped when an `author:` line already exists). The upstream
`metadata.skill-author` is left untouched as the original-author record; the new
top-level `author` is the vendor attribution.

**Agents — single string.** Synthesized frontmatter (Section C) carries
`author: "K-Dense, Inc. via galeep"`. The agents corpus is uniformly K-Dense / MIT and
has no per-file author, so one string is correct.

### D2. License correctness

The current build stamps every plugin's `plugin.json` `license` from the upstream
blanket (`MIT`), which is wrong for plugins whose skills are GPL/CC/proprietary. Fix:

- Read each skill's `license` frontmatter value during the build.
- Normalize cosmetic variants to a canonical token (`"MIT license"`, `"MIT"`,
  `"MIT License"` → `MIT`; `"Apache-2.0 license"` → `Apache-2.0`; `"CC-BY-4.0"` and the
  CC URL → `CC-BY-4.0`; etc.). A small normalization map handles the observed values;
  unrecognized strings pass through verbatim and count as their own distinct license.
- A plugin's `plugin.json` `license` is the single normalized license when all its
  member skills agree, otherwise the literal string `mixed (see individual skills)`.
- The plugin `README.md` gains a per-skill license line so the true license of each
  skill is always visible even when the plugin is `mixed`.
- Agent plugins are uniformly `MIT` (the agents repo license), so this collapses to a
  single value for them.

This is the one place the PR widens past the original "authors" ask, included because
the mis-stamp is an active correctness bug surfaced while scanning the skills.

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
- Attribution injector applied to every built skill `SKILL.md` (D1, per-skill derived)
  and used when synthesizing agent frontmatter (C).
- License resolver (D2): read + normalize each skill's license, set each plugin's
  `plugin.json` license to the uniform value or `mixed (see individual skills)`, and
  emit a per-skill license line in the plugin `README.md`.

## Implementation order

1. Add the `vendor/scientific-agents` submodule pinned at its SHA; re-pin
   `vendor/scientific-agent-skills` to main HEAD; add/adjust the `upstreams` entries
   (with `pinned_sha`) in `plugins.yaml`.
2. Author `taxonomy/rules.yaml` (seed rules + overrides for the 8 agent stragglers).
3. Write `scripts/seed_assignments.py`; generate `taxonomy/skills.yaml` and
   `taxonomy/agents.yaml`.
4. **Review the tables** — finalize the E split boundaries, confirm the 8 orphan/new
   skills land per the proposed-homes table, spot-check agent assignments. Commit the
   locked tables.
5. Add the ~15 agent plugin metadata entries to `plugins.yaml`; remove the inline skill
   lists.
6. Extend `render.py`: `pinned_sha`, table loading, coverage gate, `build_agents_plugin`,
   per-skill attribution injector, license resolver, skill membership from table.
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
- **License normalization missing a variant.** Unrecognized license strings pass through
  verbatim and count as their own token, so a missed variant degrades to `mixed (see
  individual skills)` (conservative) rather than a false uniform claim; the per-skill
  README line keeps the true value visible.

## Provenance and attribution

- Agents: vendored from `K-Dense-AI/scientific-agents` @ `896ed6e`, MIT, © K-Dense, Inc.;
  each carries `author: "K-Dense, Inc. via galeep"`.
- Skills: vendored from `K-Dense-AI/scientific-agent-skills` @ `b2a969e`; each carries
  `author: "{original skill-author} via galeep"` (or `"via galeep"` when none), and
  retains upstream `metadata.skill-author` as the original-author record.
- Per-plugin `README.md` and `plugin.json` record the upstream repo, pinned SHA, and the
  resolved license (single normalized value or `mixed (see individual skills)`, with a
  per-skill license line in the README).
