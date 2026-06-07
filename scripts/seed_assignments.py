#!/usr/bin/env python3
"""Seed/refresh taxonomy/{skills,agents}.yaml from taxonomy/rules.yaml.

Preserves existing human assignments; appends newly-seen upstream items as
UNASSIGNED (or as classified by rules when a rule matches). Re-runnable.

NOT part of the build. render.py reads only the locked tables this writes.
Skills classify against the bare slug; agents against slug+profession+work_mode.
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
    present = sorted(
        p.name for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    )
    table = _load(REPO / "taxonomy" / "skills.yaml")
    spec = RULES["skills"]
    rules = classify.compile_rules(spec)
    overrides = spec.get("overrides", {})
    for slug in present:
        if slug in table:
            continue
        # Skills match on the bare slug (anchored patterns like ^bids$ rely on it).
        table[slug] = overrides.get(slug) or classify.classify_text(slug, rules) or "UNASSIGNED"
    _dump(REPO / "taxonomy" / "skills.yaml", table)
    return present, table


def seed_agents():
    catalog = json.loads(
        (REPO / "vendor" / "scientific-agents" / "catalog.json").read_text()
    )["agents"]
    table = _load(REPO / "taxonomy" / "agents.yaml")
    spec = RULES["agents"]
    rules = classify.compile_rules(spec)
    overrides = spec.get("overrides", {})
    for a in catalog:
        slug = a["slug"]
        if slug in table:
            continue
        table[slug] = classify.assign(
            slug, a["profession"], a["work_mode"], rules, overrides
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
