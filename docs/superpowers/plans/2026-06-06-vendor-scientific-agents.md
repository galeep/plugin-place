# Vendor scientific-agents + unified grouping methodology — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor K-Dense's 503 `scientific-agents` profiles as Claude Code subagents grouped into ~15 domain plugins, and replace hand-listed skill membership with a coverage-gated assignment-table methodology that also fixes attribution and license metadata for the existing skills.

**Architecture:** `plugins.yaml` keeps plugin metadata only; membership lives in committed `taxonomy/*.yaml` tables seeded by rules and locked by human review. `scripts/render.py` gains table-driven membership, a coverage gate, agent→subagent conversion, per-skill attribution injection, and per-skill license resolution. New pure logic lives in `scripts/lib/*` (small, unit-tested) so `render.py` stays an orchestrator. Both upstreams are SHA-pinned.

**Tech Stack:** Python 3 + PyYAML (already in `.venv`), pytest (added here), bash build scripts, git submodules, `gh`/`jq` for CI.

**Spec:** `docs/superpowers/specs/2026-06-06-vendor-scientific-agents-design.md`

---

## File Structure

New, unit-tested pure logic (one responsibility each):

- `scripts/lib/__init__.py` — package marker.
- `scripts/lib/frontmatter.py` — split frontmatter, read top-level and nested fields, inject an `author:` line at string level (no YAML round-trip).
- `scripts/lib/attribution.py` — compute the vendor author string for skills and agents.
- `scripts/lib/licenses.py` — normalize a license string to a canonical token; resolve a plugin's license (uniform value or `mixed` sentinel).
- `scripts/lib/classify.py` — apply ordered keyword rules to a slug (seed-time only).
- `scripts/lib/tables.py` — load assignment tables; run the coverage gate.
- `scripts/lib/agents.py` — synthesize a subagent `.md` (frontmatter from catalog + verbatim body).

New data + tooling:

- `taxonomy/rules.yaml` — ordered `rules:` (domain + pattern) and `overrides:` (slug → domain). Read only by the seed generator.
- `taxonomy/skills.yaml` — `<skill>: <plugin>` for every skill.
- `taxonomy/agents.yaml` — `<agent-slug>: <plugin>` for every agent.
- `scripts/seed_assignments.py` — CLI: classify upstream items via rules, write/update the two tables, append new items as `UNASSIGNED`.
- `tests/` — pytest unit tests for each `lib` module.
- `pytest.ini` — minimal pytest config (testpaths, rootdir).

Modified:

- `scripts/render.py` — accept `pinned_sha`; load tables; coverage gate; derive skill membership from `taxonomy/skills.yaml`; new `build_agents_plugin`; apply attribution + license resolution to skill plugins. Existing `build_built_plugin`/`build_vendored_*`/patch logic left intact except the membership source and the attribution/license calls.
- `scripts/build.sh` — submodule presence check covers `vendor/scientific-agents`.
- `plugins.yaml` — `pinned_sha` on both K-Dense upstreams; new `scientific-agents` upstream; ~15 `kind: agents` plugin entries; inline `skills:` lists removed.
- `.gitmodules` — `vendor/scientific-agents` submodule.
- `.github/workflows/*` — drift check extended to the new submodule + coverage-gate assertion.

---

## Task 1: Test scaffold

**Files:**
- Create: `pytest.ini`
- Create: `scripts/lib/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Add pytest to the venv**

Run:
```bash
cd ~/work/plugin-place && .venv/bin/pip install pytest
```
Expected: `Successfully installed pytest-...`

- [ ] **Step 2: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 3: Create package markers**

`scripts/lib/__init__.py`:
```python
"""Pure helpers for render.py — small, unit-tested, no I/O side effects."""
```
`tests/__init__.py`: (empty file)

- [ ] **Step 4: Write a smoke test that imports the lib package**

`tests/test_smoke.py`:
```python
import importlib

def test_lib_package_imports():
    mod = importlib.import_module("scripts.lib")
    assert mod is not None
```

- [ ] **Step 5: Run it**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add pytest.ini scripts/lib/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "test: add pytest scaffold for render.py helpers"
```

---

## Task 2: Frontmatter read/split helpers

**Files:**
- Create: `scripts/lib/frontmatter.py`
- Test: `tests/test_frontmatter.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_frontmatter.py`:
```python
from scripts.lib import frontmatter as fm

SKILL = (
    "---\n"
    "name: rdkit\n"
    "description: Cheminformatics toolkit.\n"
    "license: BSD-3-Clause license\n"
    "metadata:\n"
    '  version: "1.0"\n'
    "  skill-author: K-Dense Inc.\n"
    "---\n"
    "# RDKit\nbody line\n"
)

NESTED_QUOTED = (
    "---\n"
    "name: bids\n"
    "description: >\n"
    "  multi line\n"
    "license: https://creativecommons.org/licenses/by/4.0/\n"
    "metadata:\n"
    '  version: "1.0"\n'
    "  skill-author: Yaroslav Halchenko\n"
    "---\n"
    "body\n"
)

def test_split_returns_frontmatter_and_body():
    head, body = fm.split_frontmatter(SKILL)
    assert "name: rdkit" in head
    assert body.startswith("# RDKit")

def test_split_no_frontmatter():
    head, body = fm.split_frontmatter("no frontmatter here\n")
    assert head is None
    assert body == "no frontmatter here\n"

def test_get_top_level_field():
    head, _ = fm.split_frontmatter(SKILL)
    assert fm.get_field(head, "name") == "rdkit"
    assert fm.get_field(head, "license") == "BSD-3-Clause license"
    assert fm.get_field(head, "author") is None

def test_get_nested_field():
    head, _ = fm.split_frontmatter(SKILL)
    assert fm.get_nested_field(head, "metadata", "skill-author") == "K-Dense Inc."

def test_get_nested_field_other_skill():
    head, _ = fm.split_frontmatter(NESTED_QUOTED)
    assert fm.get_nested_field(head, "metadata", "skill-author") == "Yaroslav Halchenko"
    assert fm.get_field(head, "license") == "https://creativecommons.org/licenses/by/4.0/"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_frontmatter.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.lib.frontmatter`

- [ ] **Step 3: Implement `scripts/lib/frontmatter.py`**

```python
"""Read and minimally edit YAML frontmatter without reserializing it.

String-level on purpose: a YAML round-trip would reorder keys and reflow
multiline `description:` blocks. We only ever READ scalar fields and INSERT
one line, so substring handling is sufficient and lossless.
"""
import re

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def split_frontmatter(text):
    """Return (frontmatter_str, body_str). frontmatter_str is None if absent."""
    m = _FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def get_field(frontmatter, key):
    """First top-level (zero-indent) scalar value for `key`, or None."""
    if frontmatter is None:
        return None
    for line in frontmatter.splitlines():
        m = re.match(rf"^{re.escape(key)}:[ \t]*(.+?)[ \t]*$", line)
        if m:
            return _unquote(m.group(1))
    return None


def get_nested_field(frontmatter, parent, key):
    """Value of `key` nested under a top-level `parent:` block, or None."""
    if frontmatter is None:
        return None
    in_parent = False
    for line in frontmatter.splitlines():
        if re.match(rf"^{re.escape(parent)}:[ \t]*$", line):
            in_parent = True
            continue
        if in_parent:
            if re.match(r"^\S", line):  # dedent: left the block
                in_parent = False
                continue
            m = re.match(rf"^[ \t]+{re.escape(key)}:[ \t]*(.+?)[ \t]*$", line)
            if m:
                return _unquote(m.group(1))
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_frontmatter.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/frontmatter.py tests/test_frontmatter.py
git commit -m "feat: frontmatter read/split helpers for render"
```

---

## Task 3: Author injection (idempotent, string-level)

**Files:**
- Modify: `scripts/lib/frontmatter.py` (add `inject_author`, `yaml_dq`)
- Test: `tests/test_inject_author.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_inject_author.py`:
```python
from scripts.lib import frontmatter as fm

SKILL = (
    "---\n"
    "name: rdkit\n"
    "description: tool.\n"
    "metadata:\n"
    "  skill-author: K-Dense Inc.\n"
    "---\n"
    "body\n"
)

def test_inject_after_name_line():
    out = fm.inject_author(SKILL, "K-Dense Inc. via galeep")
    head, _ = fm.split_frontmatter(out)
    assert fm.get_field(head, "author") == "K-Dense Inc. via galeep"
    # inserted immediately after name:
    lines = head.splitlines()
    assert lines[0] == "name: rdkit"
    assert lines[1] == 'author: "K-Dense Inc. via galeep"'

def test_inject_is_idempotent():
    once = fm.inject_author(SKILL, "K-Dense Inc. via galeep")
    twice = fm.inject_author(once, "DIFFERENT via galeep")
    assert once == twice  # existing author: is never overwritten

def test_inject_preserves_body_and_metadata():
    out = fm.inject_author(SKILL, "X via galeep")
    head, body = fm.split_frontmatter(out)
    assert body == "body\n"
    assert fm.get_nested_field(head, "metadata", "skill-author") == "K-Dense Inc."

def test_yaml_dq_escapes_quotes():
    assert fm.yaml_dq('a "b"') == '"a \\"b\\""'

def test_inject_raises_without_frontmatter():
    import pytest
    with pytest.raises(ValueError):
        fm.inject_author("no frontmatter\n", "x")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_inject_author.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'inject_author'`

- [ ] **Step 3: Add to `scripts/lib/frontmatter.py`**

Append:
```python
def yaml_dq(value):
    """Double-quote a scalar for YAML, escaping backslashes and quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def inject_author(text, author):
    """Insert `author: "<author>"` after the top-level `name:` line.

    Idempotent: if a top-level `author:` already exists, return text unchanged.
    Raises ValueError if there is no frontmatter to edit.
    """
    head, body = split_frontmatter(text)
    if head is None:
        raise ValueError("inject_author: no frontmatter present")
    if get_field(head, "author") is not None:
        return text
    author_line = f"author: {yaml_dq(author)}"
    out, inserted = [], False
    for line in head.splitlines():
        out.append(line)
        if not inserted and re.match(r"^name:[ \t]*", line):
            out.append(author_line)
            inserted = True
    if not inserted:
        out.insert(0, author_line)
    return "---\n" + "\n".join(out) + "\n---\n" + body
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_inject_author.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/frontmatter.py tests/test_inject_author.py
git commit -m "feat: idempotent string-level author injection"
```

---

## Task 4: Attribution strings

**Files:**
- Create: `scripts/lib/attribution.py`
- Test: `tests/test_attribution.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_attribution.py`:
```python
from scripts.lib import attribution as attr

def test_skill_author_with_origin():
    assert attr.skill_author("K-Dense Inc.") == "K-Dense Inc. via galeep"
    assert attr.skill_author("Yaroslav Halchenko") == "Yaroslav Halchenko via galeep"

def test_skill_author_without_origin():
    assert attr.skill_author(None) == "via galeep"
    assert attr.skill_author("") == "via galeep"
    assert attr.skill_author("   ") == "via galeep"

def test_agent_author_constant():
    assert attr.AGENT_AUTHOR == "K-Dense, Inc. via galeep"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_attribution.py -v`
Expected: FAIL `ModuleNotFoundError: scripts.lib.attribution`

- [ ] **Step 3: Implement `scripts/lib/attribution.py`**

```python
"""Vendor attribution strings. The mark is 'via galeep' over the original author."""

AGENT_AUTHOR = "K-Dense, Inc. via galeep"


def skill_author(original):
    """`"<original> via galeep"` when an original author exists, else `"via galeep"`.

    `original` is the upstream `metadata.skill-author`; None/blank means the
    skill carries no author and we add only the vendor mark (no fabrication).
    """
    if original and original.strip():
        return f"{original.strip()} via galeep"
    return "via galeep"
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_attribution.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/attribution.py tests/test_attribution.py
git commit -m "feat: vendor attribution string helpers"
```

---

## Task 5: License normalization + resolution

**Files:**
- Create: `scripts/lib/licenses.py`
- Test: `tests/test_licenses.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_licenses.py`:
```python
from scripts.lib import licenses as lic

def test_normalize_mit_variants():
    assert lic.normalize("MIT") == "MIT"
    assert lic.normalize("MIT license") == "MIT"
    assert lic.normalize("MIT License") == "MIT"

def test_normalize_apache_and_bsd():
    assert lic.normalize("Apache-2.0 license") == "Apache-2.0"
    assert lic.normalize("Apache-2.0") == "Apache-2.0"
    assert lic.normalize("BSD-3-Clause license") == "BSD-3-Clause"
    assert lic.normalize("BSD-3-Clause") == "BSD-3-Clause"

def test_normalize_cc_by():
    assert lic.normalize("CC-BY-4.0") == "CC-BY-4.0"
    assert lic.normalize("https://creativecommons.org/licenses/by/4.0/") == "CC-BY-4.0"

def test_normalize_unknown_and_none():
    assert lic.normalize(None) == "Unknown"
    assert lic.normalize("") == "Unknown"
    assert lic.normalize("Unknown") == "Unknown"

def test_normalize_passthrough():
    weird = "CeCILL FREE SOFTWARE LICENSE AGREEMENT"
    assert lic.normalize(weird) == weird

def test_resolve_uniform():
    assert lic.resolve_plugin_license(["MIT", "MIT", "MIT"]) == "MIT"

def test_resolve_mixed():
    assert lic.resolve_plugin_license(["MIT", "GPL-3.0"]) == "mixed (see individual skills)"

def test_resolve_empty():
    assert lic.resolve_plugin_license([]) == "Unknown"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_licenses.py -v`
Expected: FAIL `ModuleNotFoundError: scripts.lib.licenses`

- [ ] **Step 3: Implement `scripts/lib/licenses.py`**

```python
"""Normalize the heterogeneous `license:` strings in upstream skills and resolve
a single plugin-level license (or a 'mixed' sentinel)."""

MIXED = "mixed (see individual skills)"

_NORMALIZE = {
    "mit": "MIT",
    "mit license": "MIT",
    "bsd license": "BSD",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-2-clause license": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd-3-clause license": "BSD-3-Clause",
    "apache-2.0": "Apache-2.0",
    "apache-2.0 license": "Apache-2.0",
    "gpl-2.0 license": "GPL-2.0",
    "gpl-3.0 license": "GPL-3.0",
    "gplv3 license": "GPL-3.0",
    "cc-by-4.0": "CC-BY-4.0",
    "https://creativecommons.org/licenses/by/4.0/": "CC-BY-4.0",
    "unknown": "Unknown",
    "": "Unknown",
}


def normalize(raw):
    """Canonical token for a raw license string. Unknown values pass through
    verbatim (so a missed variant degrades to 'mixed', never a false uniform)."""
    if raw is None:
        return "Unknown"
    key = raw.strip().lower()
    if key in _NORMALIZE:
        return _NORMALIZE[key]
    return raw.strip() or "Unknown"


def resolve_plugin_license(normalized_licenses):
    """Single value if all member licenses agree, else the MIXED sentinel.
    Empty input -> 'Unknown'."""
    uniq = sorted(set(normalized_licenses))
    if not uniq:
        return "Unknown"
    if len(uniq) == 1:
        return uniq[0]
    return MIXED
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_licenses.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/licenses.py tests/test_licenses.py
git commit -m "feat: license normalization and per-plugin resolution"
```

---

## Task 6: Classification rules engine (seed-time)

**Files:**
- Create: `scripts/lib/classify.py`
- Test: `tests/test_classify.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_classify.py`:
```python
from scripts.lib import classify

RULES = [
    ("physics-astro", r"physicist|astronom"),
    ("chemistry", r"chemist"),
    ("engineering", r"engineer"),
]

def test_first_match_wins():
    assert classify.classify_text("astrophysicist astronomer", RULES) == "physics-astro"

def test_later_rule_matches():
    assert classify.classify_text("organic chemist", RULES) == "chemistry"

def test_no_match_returns_none():
    assert classify.classify_text("philosopher", RULES) is None

def test_compile_rules_from_spec():
    spec = {"rules": [{"domain": "chemistry", "pattern": "chemist"}]}
    compiled = classify.compile_rules(spec)
    assert compiled[0][0] == "chemistry"
    assert classify.classify_text("a chemist", compiled) == "chemistry"

def test_overrides_take_precedence():
    spec = {
        "rules": [{"domain": "engineering", "pattern": "engineer"}],
        "overrides": {"chemical-engineer": "chemistry"},
    }
    compiled = classify.compile_rules(spec)
    assert classify.assign("chemical-engineer", "chemical engineer", "x", compiled, spec.get("overrides", {})) == "chemistry"
    assert classify.assign("civil-engineer", "civil engineer", "x", compiled, {}) == "engineering"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_classify.py -v`
Expected: FAIL `ModuleNotFoundError: scripts.lib.classify`

- [ ] **Step 3: Implement `scripts/lib/classify.py`**

```python
"""Ordered keyword classifier used only by the seed generator (never the build).

A rules spec is `{"rules": [{"domain","pattern"}], "overrides": {slug: domain}}`.
"""
import re


def compile_rules(spec):
    """Return [(domain, compiled_regex), ...] in spec order."""
    return [(r["domain"], re.compile(r["pattern"])) for r in spec["rules"]]


def classify_text(haystack, compiled_rules):
    """First domain whose pattern matches `haystack`, else None."""
    for domain, rx in compiled_rules:
        if rx.search(haystack):
            return domain
    return None


def assign(slug, profession, work_mode, compiled_rules, overrides):
    """Resolve a single item to a domain: override first, then rules over the
    lowercased slug+profession+work_mode haystack. None if nothing matches."""
    if slug in overrides:
        return overrides[slug]
    haystack = " ".join([slug, profession, work_mode]).lower()
    return classify_text(haystack, compiled_rules)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_classify.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/classify.py tests/test_classify.py
git commit -m "feat: seed-time keyword classifier with overrides"
```

---

## Task 7: Assignment-table load + coverage gate

**Files:**
- Create: `scripts/lib/tables.py`
- Test: `tests/test_tables.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tables.py`:
```python
import pytest
from scripts.lib import tables

def test_gate_passes_when_complete():
    table = {"a": "plug-x", "b": "plug-y"}
    tables.coverage_gate({"a", "b"}, table, {"plug-x", "plug-y"}, "skill")
    # no exception == pass

def test_gate_fails_on_missing_item():
    table = {"a": "plug-x"}
    with pytest.raises(SystemExit) as e:
        tables.coverage_gate({"a", "b"}, table, {"plug-x"}, "skill")
    assert "b" in str(e.value)

def test_gate_fails_on_unassigned():
    table = {"a": "UNASSIGNED"}
    with pytest.raises(SystemExit) as e:
        tables.coverage_gate({"a"}, table, {"plug-x"}, "agent")
    assert "UNASSIGNED" in str(e.value)

def test_gate_fails_on_unknown_plugin():
    table = {"a": "ghost-plugin"}
    with pytest.raises(SystemExit) as e:
        tables.coverage_gate({"a"}, table, {"plug-x"}, "skill")
    assert "ghost-plugin" in str(e.value)

def test_gate_fails_on_stale_entry():
    table = {"a": "plug-x", "gone": "plug-x"}
    with pytest.raises(SystemExit) as e:
        tables.coverage_gate({"a"}, table, {"plug-x"}, "skill")
    assert "gone" in str(e.value) and "stale" in str(e.value)

def test_members_for_plugin():
    table = {"a": "plug-x", "b": "plug-y", "c": "plug-x"}
    assert tables.members_for(table, "plug-x") == ["a", "c"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_tables.py -v`
Expected: FAIL `ModuleNotFoundError: scripts.lib.tables`

- [ ] **Step 3: Implement `scripts/lib/tables.py`**

```python
"""Load assignment tables and enforce the coverage gate.

The gate is the guarantee that no upstream item is ever silently dropped:
every present item must be assigned to a real plugin, and the table must not
carry stale entries for items that left upstream.
"""
import yaml


def load_table(path):
    """Load a `<slug>: <plugin>` YAML mapping; empty/missing file -> {}."""
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        return {}
    return data or {}


def members_for(table, plugin_name):
    """Sorted slugs assigned to `plugin_name`."""
    return sorted(s for s, p in table.items() if p == plugin_name)


def coverage_gate(present_items, table, valid_plugins, kind):
    """Abort (SystemExit) with every problem listed if the table does not exactly
    and validly cover `present_items`.

    present_items: set of slugs found in the submodule.
    table:        dict slug -> plugin (or 'UNASSIGNED').
    valid_plugins: set of plugin names declared in plugins.yaml.
    kind:         'skill' | 'agent', for messages.
    """
    errors = []
    for item in sorted(present_items):
        if item not in table:
            errors.append(f"{kind} {item!r}: not in assignment table")
        elif not table[item] or table[item] == "UNASSIGNED":
            errors.append(f"{kind} {item!r}: UNASSIGNED")
        elif table[item] not in valid_plugins:
            errors.append(
                f"{kind} {item!r}: plugin {table[item]!r} not declared in plugins.yaml"
            )
    for item in sorted(table):
        if item not in present_items:
            errors.append(f"{kind} {item!r}: in table but not in submodule (stale)")
    if errors:
        raise SystemExit("coverage gate FAILED:\n  " + "\n  ".join(errors))
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_tables.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/tables.py tests/test_tables.py
git commit -m "feat: assignment-table loader and coverage gate"
```

---

## Task 8: Agent → subagent synthesis

**Files:**
- Create: `scripts/lib/agents.py`
- Test: `tests/test_agents.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_agents.py`:
```python
from scripts.lib import agents
from scripts.lib import frontmatter as fm

PROFILE = "# AGENTS.md — Astrophysicist Agent\n\nYou are an astrophysicist.\n"

def test_synth_has_expected_frontmatter():
    out = agents.synth_subagent(
        profile_text=PROFILE,
        slug="astrophysicist",
        profession="Astrophysicist",
        summary="Reasons from radiative transfer and GR.",
        author="K-Dense, Inc. via galeep",
    )
    head, body = fm.split_frontmatter(out)
    assert fm.get_field(head, "name") == "astrophysicist"
    assert fm.get_field(head, "description") == "Astrophysicist: Reasons from radiative transfer and GR."
    assert fm.get_field(head, "author") == "K-Dense, Inc. via galeep"

def test_body_is_verbatim():
    out = agents.synth_subagent(PROFILE, "x", "X", "s.", "a")
    _, body = fm.split_frontmatter(out)
    assert body == PROFILE

def test_description_quotes_safe_for_colons():
    out = agents.synth_subagent(PROFILE, "x", "X", "a: b: c", "a")
    head, _ = fm.split_frontmatter(out)
    assert fm.get_field(head, "description") == "X: a: b: c"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_agents.py -v`
Expected: FAIL `ModuleNotFoundError: scripts.lib.agents`

- [ ] **Step 3: Implement `scripts/lib/agents.py`**

```python
"""Convert a K-Dense AGENTS.md profile into a Claude Code subagent file.

Frontmatter is synthesized from catalog metadata; the profile body is kept
verbatim (faithful provenance, drift detection stays meaningful).
"""
from .frontmatter import yaml_dq


def synth_subagent(profile_text, slug, profession, summary, author):
    """Return subagent `.md` content: synthesized frontmatter + verbatim body."""
    description = f"{profession}: {summary}"
    head = "\n".join([
        "---",
        f"name: {slug}",
        f"description: {yaml_dq(description)}",
        f"author: {yaml_dq(author)}",
        "---",
        "",
    ])
    return head + profile_text
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_agents.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the whole suite**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest -v`
Expected: PASS (all tasks 1-8 green)

- [ ] **Step 6: Commit**

```bash
git add scripts/lib/agents.py tests/test_agents.py
git commit -m "feat: AGENTS.md to Claude Code subagent synthesis"
```

---

## Task 9: Vendor the agents submodule + bump the skills pin

**Files:**
- Modify: `.gitmodules`
- Modify: `plugins.yaml` (upstreams block)
- Modify: `scripts/build.sh`
- New submodule: `vendor/scientific-agents`

- [ ] **Step 1: Add the agents submodule pinned at the SHA**

```bash
cd ~/work/plugin-place
git submodule add https://github.com/K-Dense-AI/scientific-agents.git vendor/scientific-agents
git -C vendor/scientific-agents checkout 896ed6ed1e1a6686572db06ca59fd1c1b0055ca7
git add .gitmodules vendor/scientific-agents
```
Expected: `vendor/scientific-agents` present; `catalog.json` and `scientific-agents/` exist inside it.

- [ ] **Step 2: Re-pin the skills submodule to main HEAD**

```bash
cd ~/work/plugin-place
git -C vendor/scientific-agent-skills fetch origin
git -C vendor/scientific-agent-skills checkout b2a969eb56d92c454e682138cd93587d77b64b11
git add vendor/scientific-agent-skills
```
Expected: `git -C vendor/scientific-agent-skills rev-parse HEAD` prints `b2a969eb...`; `skills/bulk-rnaseq` and `skills/pathway-enrichment` now exist.

- [ ] **Step 3: Update `plugins.yaml` upstreams**

Replace `pinned_tag: v2.45.0` for `scientific-agent-skills` with:
```yaml
  scientific-agent-skills:
    submodule: vendor/scientific-agent-skills
    skills_root: skills
    pinned_sha: b2a969eb56d92c454e682138cd93587d77b64b11
    upstream_repo: K-Dense-AI/scientific-agent-skills
    license: MIT   # fallback only; real license resolved per-skill
```
Add a new upstream:
```yaml
  scientific-agents:
    submodule: vendor/scientific-agents
    agents_root: scientific-agents
    catalog: catalog.json
    pinned_sha: 896ed6ed1e1a6686572db06ca59fd1c1b0055ca7
    upstream_repo: K-Dense-AI/scientific-agents
    license: MIT
```

- [ ] **Step 4: Extend the submodule presence check in `scripts/build.sh`**

Change the loop line:
```bash
for sub in vendor/scientific-agent-skills vendor/claude-scientific-writer vendor/caveman; do
```
to:
```bash
for sub in vendor/scientific-agent-skills vendor/claude-scientific-writer vendor/caveman vendor/scientific-agents; do
```

- [ ] **Step 5: Verify the trees are present**

Run:
```bash
cd ~/work/plugin-place && ls vendor/scientific-agents/scientific-agents | wc -l && ls vendor/scientific-agent-skills/skills/bulk-rnaseq/SKILL.md
```
Expected: `503` (agent dirs) and the bulk-rnaseq SKILL.md path printed.

- [ ] **Step 6: Commit**

```bash
git add .gitmodules vendor/scientific-agents vendor/scientific-agent-skills plugins.yaml scripts/build.sh
git commit -m "chore: vendor scientific-agents submodule; bump skills pin to main"
```

---

## Task 10: Seed generator + initial tables

**Files:**
- Create: `taxonomy/rules.yaml`
- Create: `scripts/seed_assignments.py`
- Create (generated): `taxonomy/skills.yaml`, `taxonomy/agents.yaml`

- [ ] **Step 1: Write `taxonomy/rules.yaml`**

Use the spec's draft taxonomy. Agent rules (ordered; first match wins) plus skill rules and overrides. Start from this skeleton and the keyword sets validated during brainstorming (see spec §E). Example shape:
```yaml
# Seed rules for scripts/seed_assignments.py. NOT read by the build.
agents:
  rules:
    - {domain: sci-agents-clinical, pattern: "clinical|physician|epidemiolog|pharmacovigilance|regulatory-affairs|clinical-trial|genetic-counsel|public-health|health-econ|health-inform|translational|precision-medicine|global-health|occupational-health|environmental-health"}
    - {domain: sci-agents-medical-specialties, pattern: "surgeon|oncolog|cardiolog|radiolog|patholog|anesthesi|dermatolog|neurolog|hematolog|hepatolog|nephrolog|endocrinolog|ophthalmolog|immunotherapy|gene-therapy|nuclear-medicine|medical-physic|radiation-oncology|emergency-medicine|critical-care|palliative|rehabilitation|audiolog|dentist|gerontolog|sleep-scientist|exercise-physiolog|sports-scien|comparative-medicine|regenerative|reproductive-bio|embryolog|vaccinolog|infectious-disease|toxicolog|pharmacolog|pharmacokinet|pharmaceutical|medical-genetic|physician|surgeon"}
    # ... molecular-cell-biology, organismal-eco-biology, physics, astronomy-space,
    #     earth-environment, ocean-atmos-climate, engineering,
    #     electrical-computer-hw, cs-ai-data, agri-food-vet, math-stats-or,
    #     chemistry, materials-nano (full keyword sets per spec §E)
  overrides:
    algorithms-researcher: sci-agents-cs-ai-data
    antimicrobial-resistance-scientist: sci-agents-molecular-cell-biology
    astrodynamicist: sci-agents-astronomy-space
    geotechnical-scientist: sci-agents-earth-environment
    microbiome-scientist: sci-agents-molecular-cell-biology
    polymer-scientist: sci-agents-materials-nano
    renewable-energy-scientist: sci-agents-engineering
    urban-infrastructure-planner: sci-agents-engineering
skills:
  # Skills keep their existing plugin grouping. Seed from the current plugins.yaml
  # inline lists; the generator only fills NEW/orphan skills via these rules.
  rules:
    - {domain: sci-bioinformatics-genomics, pattern: "rnaseq|pathway-enrichment|nextflow|pacsomatic"}
    - {domain: sci-medical-imaging, pattern: "^bids$"}
    - {domain: sci-scientific-communication, pattern: "exa-search|liteparse"}
    - {domain: sci-research-methodology, pattern: "autoskill"}
  overrides: {}
```

> NOTE: the full agent keyword sets are the ones validated in the brainstorming
> classifier (spec §E). Port them verbatim into the `pattern:` fields. Do not
> abbreviate — every domain needs its complete keyword alternation.

- [ ] **Step 2: Write `scripts/seed_assignments.py`**

```python
#!/usr/bin/env python3
"""Seed/refresh taxonomy/{skills,agents}.yaml from taxonomy/rules.yaml.

Preserves existing human assignments; appends newly-seen upstream items as
UNASSIGNED (or as classified by rules when a rule matches). Re-runnable.
"""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.lib import classify  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
RULES = yaml.safe_load((REPO / "taxonomy" / "rules.yaml").read_text())


def _load(path):
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


def _dump(path, table):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(table, sort_keys=True, default_flow_style=False))


def seed_skills():
    skills_dir = REPO / "vendor" / "scientific-agent-skills" / "skills"
    present = sorted(p.name for p in skills_dir.iterdir()
                     if p.is_dir() and (p / "SKILL.md").exists())
    table = _load(REPO / "taxonomy" / "skills.yaml")
    spec = RULES["skills"]
    rules = classify.compile_rules(spec)
    for slug in present:
        if slug in table:
            continue
        table[slug] = classify.assign(slug, slug, "", rules, spec.get("overrides", {})) or "UNASSIGNED"
    _dump(REPO / "taxonomy" / "skills.yaml", table)
    return present, table


def seed_agents():
    catalog = json.loads(
        (REPO / "vendor" / "scientific-agents" / "catalog.json").read_text()
    )["agents"]
    table = _load(REPO / "taxonomy" / "agents.yaml")
    spec = RULES["agents"]
    rules = classify.compile_rules(spec)
    for a in catalog:
        slug = a["slug"]
        if slug in table:
            continue
        table[slug] = classify.assign(
            slug, a["profession"], a["work_mode"], rules, spec.get("overrides", {})
        ) or "UNASSIGNED"
    _dump(REPO / "taxonomy" / "agents.yaml", table)
    return [a["slug"] for a in catalog], table


if __name__ == "__main__":
    sp, st = seed_skills()
    ap, at = seed_agents()
    su = sum(1 for v in st.values() if v == "UNASSIGNED")
    au = sum(1 for v in at.values() if v == "UNASSIGNED")
    print(f"skills: {len(sp)} present, {su} UNASSIGNED")
    print(f"agents: {len(ap)} present, {au} UNASSIGNED")
```

- [ ] **Step 3: Pre-seed the skills table from the current inline lists**

The existing `plugins.yaml` already maps 135 skills to plugins. Convert those to `taxonomy/skills.yaml` first so the generator only has to place the 8 new/orphan skills:
```bash
cd ~/work/plugin-place && .venv/bin/python - <<'PY'
import yaml, pathlib
cfg = yaml.safe_load(pathlib.Path("plugins.yaml").read_text())
table = {}
for p in cfg["plugins"]:
    if p.get("upstream") == "scientific-agent-skills" and p["kind"] == "built":
        for s in p.get("skills", []):
            table[s] = p["name"]
out = pathlib.Path("taxonomy/skills.yaml")
out.parent.mkdir(exist_ok=True)
out.write_text(yaml.safe_dump(table, sort_keys=True))
print("pre-seeded", len(table), "skills")
PY
```
Expected: `pre-seeded 135 skills`

- [ ] **Step 4: Run the seed generator**

Run: `cd ~/work/plugin-place && .venv/bin/python scripts/seed_assignments.py`
Expected: `skills: 143 present, 0 UNASSIGNED` (135 pre-seeded + 8 placed by rules) and `agents: 503 present, 0 UNASSIGNED` (8 stragglers covered by overrides).

- [ ] **Step 5: Sanity-check the bucket sizes**

Run:
```bash
cd ~/work/plugin-place && .venv/bin/python - <<'PY'
import yaml, collections
at = yaml.safe_load(open("taxonomy/agents.yaml"))
for plug, n in sorted(collections.Counter(at.values()).items()):
    print(f"{n:4d}  {plug}")
PY
```
Expected: ~15 `sci-agents-*` buckets, none far over 50, no `UNASSIGNED`.

- [ ] **Step 6: Commit the generator + raw tables**

```bash
git add taxonomy/rules.yaml scripts/seed_assignments.py taxonomy/skills.yaml taxonomy/agents.yaml
git commit -m "feat: seed generator + initial assignment tables"
```

---

## Task 11: Human review and lock the tables (CHECKPOINT)

**Files:**
- Modify: `taxonomy/skills.yaml`, `taxonomy/agents.yaml` (manual edits)

This task is a human decision gate, not code. The executor must stop and have Gale (or the reviewer) confirm.

- [ ] **Step 1: Review the agent split boundaries**

Open `taxonomy/agents.yaml`. Confirm the ~15 buckets and move any misclassified agent to its correct plugin. Pay attention to the split seams called out in spec §E (e.g. which astronomy slugs sit in `sci-agents-astronomy-space` vs `sci-agents-physics`).

- [ ] **Step 2: Confirm the 8 orphan/new skills landed per spec §B**

Check `taxonomy/skills.yaml`: `bulk-rnaseq`, `pathway-enrichment`, `nextflow`, `pacsomatic` → `sci-bioinformatics-genomics`; `bids` → `sci-medical-imaging`; `exa-search`, `liteparse` → `sci-scientific-communication`; `autoskill` → `sci-research-methodology`.

- [ ] **Step 3: Verify no UNASSIGNED remain**

Run:
```bash
cd ~/work/plugin-place && grep -c UNASSIGNED taxonomy/skills.yaml taxonomy/agents.yaml
```
Expected: `taxonomy/skills.yaml:0` and `taxonomy/agents.yaml:0`.

- [ ] **Step 4: Commit the locked tables**

```bash
git add taxonomy/skills.yaml taxonomy/agents.yaml
git commit -m "chore: lock reviewed skill/agent assignment tables"
```

---

## Task 12: Declare plugins in plugins.yaml

**Files:**
- Modify: `plugins.yaml`

- [ ] **Step 1: Remove the inline `skills:` lists from built plugins**

For every `kind: built` plugin sourced from `scientific-agent-skills`, delete its `skills:` block. Membership now comes from `taxonomy/skills.yaml`. Keep `name`, `kind`, `upstream`, `category`, `description`.

- [ ] **Step 2: Add the ~15 agent plugin entries**

Append a new section. Each entry (repeat for all 15 from spec §E, names exactly matching `taxonomy/agents.yaml` values):
```yaml
  - name: sci-agents-clinical
    kind: agents
    upstream: scientific-agents
    category: clinical
    description: "Clinical-medicine reasoning agents: epidemiology, clinical trials, regulatory, pharmacovigilance, public/global health, and translational medicine."

  - name: sci-agents-medical-specialties
    kind: agents
    upstream: scientific-agents
    category: clinical
    description: "Medical-specialty reasoning agents: cardiology, oncology, radiology, pathology, neurology, surgery, anesthesiology, and related specialties."

  # ... 13 more sci-agents-* entries (molecular-cell-biology, organismal-eco-biology,
  #     physics, astronomy-space, earth-environment, ocean-atmos-climate, engineering,
  #     electrical-computer-hw, cs-ai-data, agri-food-vet, math-stats-or, chemistry,
  #     materials-nano), each with a one-line domain description.
```

- [ ] **Step 3: Verify plugins.yaml parses and plugin names match the tables**

Run:
```bash
cd ~/work/plugin-place && .venv/bin/python - <<'PY'
import yaml
cfg = yaml.safe_load(open("plugins.yaml"))
plugins = {p["name"] for p in cfg["plugins"]}
at = set(yaml.safe_load(open("taxonomy/agents.yaml")).values())
st = set(yaml.safe_load(open("taxonomy/skills.yaml")).values())
missing = (at | st) - plugins
print("plugins declared:", len(plugins))
print("assignment targets not declared:", sorted(missing) or "none")
assert not missing, missing
print("OK")
PY
```
Expected: `assignment targets not declared: none` then `OK`.

- [ ] **Step 4: Commit**

```bash
git add plugins.yaml
git commit -m "feat: declare agent plugins; drop inline skill lists"
```

---

## Task 13: Wire render.py

**Files:**
- Modify: `scripts/render.py`
- Test: `tests/test_render_integration.py`

- [ ] **Step 1: Add a version accessor that accepts tag or SHA**

Near the top of `render.py` helpers, add:
```python
def upstream_version(upstream):
    """Human-facing pin label: prefer tag, fall back to SHA."""
    return upstream.get("pinned_tag") or upstream.get("pinned_sha") or "unpinned"
```
Replace every `upstream["pinned_tag"]` read in `build_built_plugin`, `build_vendored_plugin`, `build_vendored_whole_plugin`, and the README writers with `upstream_version(upstream)`.

- [ ] **Step 2: Load tables + run the coverage gate in `main()`**

Add imports at top of `render.py`:
```python
from scripts.lib import tables, attribution, licenses
from scripts.lib import frontmatter as fm
from scripts.lib import agents as agents_lib
```
In `main()`, after `config = yaml.safe_load(...)` and before building, add:
```python
    skills_table = tables.load_table(REPO_ROOT / "taxonomy" / "skills.yaml")
    agents_table = tables.load_table(REPO_ROOT / "taxonomy" / "agents.yaml")
    declared = {p["name"] for p in config["plugins"]}

    sk_up = config["upstreams"]["scientific-agent-skills"]
    skills_present = {
        p.name for p in (REPO_ROOT / sk_up["submodule"] / sk_up["skills_root"]).iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    }
    tables.coverage_gate(skills_present, skills_table, declared, "skill")

    ag_up = config["upstreams"]["scientific-agents"]
    catalog = json.loads(
        (REPO_ROOT / ag_up["submodule"] / ag_up["catalog"]).read_text()
    )["agents"]
    agents_present = {a["slug"] for a in catalog}
    tables.coverage_gate(agents_present, agents_table, declared, "agent")
    catalog_by_slug = {a["slug"]: a for a in catalog}
```

- [ ] **Step 3: Derive skill membership from the table in `build_built_plugin`**

Change `build_built_plugin(plugin, upstream)` to `build_built_plugin(plugin, upstream, skills_table)` and replace the `for skill_name in plugin["skills"]:` source with:
```python
    member_skills = tables.members_for(skills_table, plugin["name"])
```
Use `member_skills` everywhere the old `plugin["skills"]` was used (the copy loop, the README skill list, the count).

- [ ] **Step 4: Inject attribution + resolve license in `build_built_plugin`**

After each skill dir is copied to `skills_dir / skill_name`, rewrite its SKILL.md and collect its license:
```python
    plugin_licenses = []
    for skill_name in member_skills:
        # ... existing copytree ...
        skill_md = skills_dir / skill_name / "SKILL.md"
        text = skill_md.read_text()
        head, _ = fm.split_frontmatter(text)
        original = fm.get_nested_field(head, "metadata", "skill-author")
        skill_md.write_text(fm.inject_author(text, attribution.skill_author(original)))
        plugin_licenses.append(licenses.normalize(fm.get_field(head, "license")))
    plugin_license = licenses.resolve_plugin_license(plugin_licenses)
```
Use `plugin_license` for the generated `plugin.json` `license` field (instead of `upstream["license"]`), and add a per-skill license line to the README.

- [ ] **Step 5: Add `build_agents_plugin`**

```python
def build_agents_plugin(plugin, upstream, agents_table, catalog_by_slug):
    name = plugin["name"]
    submodule = REPO_ROOT / upstream["submodule"]
    agents_root = submodule / upstream["agents_root"]
    plugin_dir = PLUGINS_DIR / name
    agents_dir = plugin_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    members = tables.members_for(agents_table, name)
    for slug in members:
        meta = catalog_by_slug[slug]
        profile = (agents_root / slug / "AGENTS.md").read_text()
        out = agents_lib.synth_subagent(
            profile_text=profile,
            slug=slug,
            profession=meta["profession"],
            summary=meta["summary"],
            author=attribution.AGENT_AUTHOR,
        )
        (agents_dir / f"{slug}.md").write_text(out)

    write_json(plugin_dir / ".claude-plugin" / "plugin.json", {
        "name": name,
        "version": "0.1.0",
        "description": plugin["description"],
        "author": {"name": attribution.AGENT_AUTHOR},
        "homepage": f"https://github.com/{upstream['upstream_repo']}",
        "license": upstream["license"],
        "keywords": ["scientific-agents", upstream["upstream_repo"].split("/")[1]],
    })

    agent_list = "\n".join(
        f"- `{s}` — {catalog_by_slug[s]['profession']}" for s in members
    )
    plugin_dir.joinpath("README.md").write_text(
        f"# {name}\n\n{plugin['description']}\n\n## Agents ({len(members)})\n\n"
        f"{agent_list}\n\n## Provenance\n\nVendored from "
        f"[{upstream['upstream_repo']}](https://github.com/{upstream['upstream_repo']}) "
        f"@ `{upstream_version(upstream)}`. Licensed under {upstream['license']}. "
        f"All credit to K-Dense AI. Generated by `scripts/build.sh`; edit "
        f"`taxonomy/agents.yaml`, not these files.\n"
    )
```

- [ ] **Step 6: Dispatch `kind: agents` and thread tables in `main()`**

In `clean_built_plugins`, add `"agents"` to the regenerated kinds set. In the `main()` build loop, add:
```python
        elif kind == "agents":
            build_agents_plugin(plugin, upstream, agents_table, catalog_by_slug)
            agents_built += 1
```
and pass `skills_table` into the `build_built_plugin(plugin, upstream, skills_table)` call. Add `agents_built = 0` and include it in the final print.

- [ ] **Step 7: Write an integration test for the wired build**

`tests/test_render_integration.py`:
```python
import subprocess, sys, json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

def test_build_runs_and_emits_agent_plugin():
    r = subprocess.run([sys.executable, "scripts/render.py"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # an agent plugin exists with subagent files carrying synthesized frontmatter
    sample = REPO / "plugins" / "sci-agents-chemistry" / "agents"
    mds = list(sample.glob("*.md"))
    assert mds, "no subagent files emitted"
    text = mds[0].read_text()
    assert text.startswith("---\nname: ")
    assert "via galeep" in text

def test_marketplace_lists_agent_plugins():
    data = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    names = {p["name"] for p in data["plugins"]}
    assert "sci-agents-chemistry" in names
```

- [ ] **Step 8: Run the integration test**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest tests/test_render_integration.py -v`
Expected: PASS (2 passed). If the coverage gate fires, fix the offending table entry and re-run.

- [ ] **Step 9: Commit**

```bash
git add scripts/render.py tests/test_render_integration.py
git commit -m "feat: table-driven membership, coverage gate, agent build, attribution+license in render"
```

---

## Task 14: Full build + validation

**Files:**
- Generated: `plugins/**`, `.claude-plugin/marketplace.json`, `.claude-plugin/provenance.json`

- [ ] **Step 1: Run the full build**

Run: `cd ~/work/plugin-place && ./scripts/build.sh`
Expected: ends with `render.py: built=... agents=15 ... total=...` and `build.sh: done`, no traceback.

- [ ] **Step 2: Validate every plugin**

Run:
```bash
cd ~/work/plugin-place && fail=0
for d in plugins/*/; do ./scripts/validate-plugin.sh "$d" >/dev/null || { echo "FAIL: $d"; fail=1; }; done
echo "validation exit: $fail"
```
Expected: `validation exit: 0`.

- [ ] **Step 3: Spot-check attribution and license on a mixed-license skill plugin**

Run:
```bash
cd ~/work/plugin-place
grep -h '^author:' plugins/sci-bioinformatics-genomics/skills/bids/SKILL.md
jq -r '.license' plugins/sci-medical-imaging/.claude-plugin/plugin.json
```
Expected: `author: "Yaroslav Halchenko via galeep"`; the medical-imaging license reflects its true value or `mixed (see individual skills)`.

- [ ] **Step 4: Spot-check an author-less skill**

Run: `grep -h '^author:' plugins/kdense-document-skills/skills/docx/SKILL.md`
Expected: `author: "via galeep"`.

- [ ] **Step 5: Confirm agent count and a sample subagent**

Run:
```bash
cd ~/work/plugin-place && find plugins -path '*/agents/*.md' | wc -l
head -4 plugins/sci-agents-chemistry/agents/*.md | head -8
```
Expected: `503` total agent files; sample shows `name:`, `description: "<Profession>: ..."`, `author: "K-Dense, Inc. via galeep"`.

- [ ] **Step 6: Run the whole test suite once more**

Run: `cd ~/work/plugin-place && .venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit the built tree**

```bash
git add plugins .claude-plugin
git commit -m "build: regenerate plugins with agents + per-skill attribution/license"
```

---

## Task 15: CI drift check + PR

**Files:**
- Modify: `.github/workflows/*.yml`

- [ ] **Step 1: Inspect the existing workflow**

Run: `cd ~/work/plugin-place && ls .github/workflows && cat .github/workflows/*.yml`
Identify the step that checks submodule pins / runs `build.sh` against `provenance.json`.

- [ ] **Step 2: Add the new submodule to the drift check**

Mirror whatever the existing check does for `scientific-agent-skills` for `scientific-agents` (compare `provenance.json` SHA to the submodule SHA), and ensure the job runs `scripts/build.sh` (which now runs the coverage gate) and `pytest`. Concrete edit depends on the file read in Step 1; keep the existing structure.

- [ ] **Step 3: Verify the workflow is valid YAML**

Run: `cd ~/work/plugin-place && .venv/bin/python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit and push**

```bash
cd ~/work/plugin-place
git add .github/workflows
git commit -m "ci: extend drift check to scientific-agents; run coverage gate + pytest"
git push -u origin feature/vendor-scientific-agents
```

- [ ] **Step 5: Run pr-review-toolkit agents before opening the PR**

Per CLAUDE.md quality gate: run `code-reviewer` and `silent-failure-hunter` over the diff; fix findings; re-run tests.

- [ ] **Step 6: Open the PR**

```bash
cd ~/work/plugin-place
gh pr create --title "Vendor scientific-agents + coverage-gated grouping methodology" \
  --body "Implements docs/superpowers/specs/2026-06-06-vendor-scientific-agents-design.md. Vendors 503 K-Dense agent profiles as ~15 sci-agents-* subagent plugins; replaces hand-listed skill membership with coverage-gated assignment tables; adds per-skill 'via galeep' attribution and per-skill license resolution; bumps the skills pin to current main."
```

- [ ] **Step 7: After CI passes, request Copilot review** (per COPILOT_REVIEW_WORKFLOW.md)

---

## Self-Review

**Spec coverage:**
- §A upstreams (agents submodule + skills bump + `pinned_sha`) → Task 9; `upstream_version` in Task 13.1.
- §B methodology (rules, two tables, seed generator, coverage gate, derived membership) → Tasks 6, 7, 10, 12, 13.
- §C agent→subagent (synth frontmatter, verbatim body, drop CLAUDE.md) → Task 8 + Task 13.5.
- §D1 attribution (per-skill derived; agents single string) → Tasks 3, 4, 13.4, 13.5.
- §D2 license (normalize, resolve, README line) → Tasks 5, 13.4.
- §E ~15 split plugins → Tasks 10–12 + checkpoint 11.
- §F render.py changes → Task 13.
- Implementation order (9 steps) → Tasks 9–15.

**Placeholder scan:** The only deferred content is the full keyword alternations in `taxonomy/rules.yaml` (Task 10.1) and the 13 remaining plugin descriptions (Task 12.2), both explicitly sourced from spec §E and the brainstorming classifier rather than invented; flagged inline as "port verbatim," not "TBD." No code step omits its code.

**Type/name consistency:** `split_frontmatter`, `get_field`, `get_nested_field`, `inject_author`, `yaml_dq` (frontmatter.py); `skill_author`, `AGENT_AUTHOR` (attribution.py); `normalize`, `resolve_plugin_license`, `MIXED` (licenses.py); `compile_rules`, `classify_text`, `assign` (classify.py); `load_table`, `members_for`, `coverage_gate` (tables.py); `synth_subagent` (agents.py); `build_agents_plugin`, `upstream_version` (render.py) are used consistently across tasks.
