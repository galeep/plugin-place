#!/usr/bin/env python3
"""
render.py — invoked by build.sh. Reads plugins.yaml and produces:
  - plugins/<name>/{.claude-plugin/plugin.json, skills/, commands/, README.md}
  - .claude-plugin/marketplace.json
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# render.py runs as a script (`python scripts/render.py`), so sys.path[0] is
# scripts/ and `from scripts.lib import ...` would fail. Add the repo root the
# same way scripts/seed_assignments.py does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.lib import tables, attribution, licenses  # noqa: E402
from scripts.lib import frontmatter as fm  # noqa: E402
from scripts.lib import agents as agents_lib  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_YAML = REPO_ROOT / "plugins.yaml"
PLUGINS_DIR = REPO_ROOT / "plugins"
PATCHES_DIR = REPO_ROOT / "patches"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def submodule_sha(path: Path) -> str:
    """Get the commit SHA of a submodule for reproducibility metadata."""
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def submodule_describe(path: Path) -> str:
    """Get the tag/description of a submodule, fall back to SHA prefix."""
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "describe", "--tags", "--exact-match"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return submodule_sha(path)[:12]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def upstream_version(upstream):
    """Human-facing pin label: prefer tag, fall back to SHA."""
    return upstream.get("pinned_tag") or upstream.get("pinned_sha") or "unpinned"


def attribute_skill_tree(skills_dir: Path, fallback_author=None) -> None:
    """Inject the `via galeep` vendor author into every SKILL.md one level under
    skills_dir. Uses each file's metadata.skill-author, else `fallback_author`,
    else a bare vendor mark. Skips files without frontmatter (nothing to edit).

    Used for vendored/vendored-whole plugins (caveman, claude-scientific-writer);
    built plugins do the same inline alongside license collection.
    """
    if not skills_dir.is_dir():
        return
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        text = skill_md.read_text()
        head, _ = fm.split_frontmatter(text)
        if head is None:
            # A SKILL.md with no YAML frontmatter is malformed (no name/description
            # either) and cannot be attributed without fabricating fields. Surface
            # it loudly rather than silently leaving it unmarked.
            print(
                f"WARN: {skill_md.relative_to(PLUGINS_DIR)} has no frontmatter; "
                f"skipping attribution (malformed skill)",
                file=sys.stderr,
            )
            continue
        original = fm.get_nested_field(head, "metadata", "skill-author")
        skill_md.write_text(
            fm.inject_author(text, attribution.skill_author(original, fallback_author))
        )


def clean_built_plugins() -> None:
    """Remove plugins/ entries that are regenerated (built + vendored).
    Local plugins (kind: local) are NEVER touched."""
    if not PLUGINS_DIR.exists():
        return
    config = yaml.safe_load(PLUGINS_YAML.read_text())
    regenerated = {
        p["name"]
        for p in config["plugins"]
        if p["kind"] in ("built", "vendored", "vendored-whole", "agents")
    }
    for entry in PLUGINS_DIR.iterdir():
        if entry.is_dir() and entry.name in regenerated:
            shutil.rmtree(entry)


def build_built_plugin(plugin: dict, upstream: dict, skills_table: dict) -> None:
    """Copy skills from upstream submodule into plugins/<name>/skills/.

    Membership comes from the locked assignment table (skills_table), not the
    plugin entry. Each vendored SKILL.md gets the `via galeep` author injected
    and its normalized license collected; the plugin's license is the resolved
    union of its members'.
    """
    name = plugin["name"]
    submodule_path = REPO_ROOT / upstream["submodule"]
    skills_root = submodule_path / upstream["skills_root"]

    plugin_dir = PLUGINS_DIR / name
    skills_dir = plugin_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    member_skills = tables.members_for(skills_table, name)

    missing = []
    for skill_name in member_skills:
        src = skills_root / skill_name
        if not src.is_dir():
            missing.append(skill_name)
            continue
        if not (src / "SKILL.md").exists():
            print(f"WARN: {name}/{skill_name} has no SKILL.md", file=sys.stderr)
        shutil.copytree(src, skills_dir / skill_name)

    if missing:
        raise SystemExit(
            f"ERROR: plugin {name!r} references skills not present in "
            f"{upstream['submodule']} @ {upstream_version(upstream)}: {missing}"
        )

    # Inject the vendor author into each copied SKILL.md and collect its
    # normalized license for the plugin-level resolution.
    plugin_licenses = []
    skill_license_lines = []
    for skill_name in member_skills:
        skill_md = skills_dir / skill_name / "SKILL.md"
        text = skill_md.read_text()
        head, _ = fm.split_frontmatter(text)
        original = fm.get_nested_field(head, "metadata", "skill-author")
        skill_md.write_text(
            fm.inject_author(
                text, attribution.skill_author(original, upstream.get("author"))
            )
        )
        normalized = licenses.normalize(fm.get_field(head, "license"))
        plugin_licenses.append(normalized)
        skill_license_lines.append(f"- `{skill_name}`: {normalized}")
    plugin_license = licenses.resolve_plugin_license(plugin_licenses)

    write_json(
        plugin_dir / ".claude-plugin" / "plugin.json",
        {
            "name": name,
            "version": "0.1.0",
            "description": plugin["description"],
            "author": {"name": "galeep"},
            "homepage": "https://github.com/galeep/plugin-place",
            "license": plugin_license,
            "keywords": ["scientific-skills", upstream["upstream_repo"].split("/")[1]],
        },
    )

    readme = plugin_dir / "README.md"
    skill_list = "\n".join(f"- `{s}`" for s in member_skills)
    license_list = "\n".join(skill_license_lines)
    readme.write_text(
        f"""# {name}

{plugin["description"]}

## Skills ({len(member_skills)})

{skill_list}

## Licenses

{license_list}

## Provenance

Built from [{upstream['upstream_repo']}](https://github.com/{upstream['upstream_repo']}) @ `{upstream_version(upstream)}`.
Skills are vendored copies; per-skill licenses are listed above. All credit to K-Dense AI.

This plugin is generated by `scripts/build.sh` from `plugins.yaml`. Edits here will be overwritten on rebuild.
"""
    )


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


def drop_non_skill_containers(skills_root_dir: Path) -> None:
    """Remove directories directly under skills/ that are not themselves skills.

    Claude Code expects skills exactly one level deep under skills/, each with a
    SKILL.md at its root. Upstreams put other things there: K-Dense's writer
    ships `document-skills/` as a container holding 4 sub-skills (those are
    split into their own `built` plugin, see kdense-document-skills), and
    caveman v2.1.0 added `skills/generated/`, a build artifact holding per-agent
    pack.json files for aider/codex/gemini/hermes/opencode. Either way a
    SKILL.md-less directory fails validate-plugin.sh, so drop it.

    Only DIRECTORIES are dropped. Loose files under skills/ (caveman v2.1.0 also
    added compile.mjs, registry.json, verbs-gate.mjs, native-core.md,
    engine-mcp-tools.json) are left alone: they do not trip the validator, and
    upstream's own skills may reference them.
    """
    if not skills_root_dir.is_dir():
        return
    for container in sorted(skills_root_dir.iterdir()):
        if not container.is_dir() or (container / "SKILL.md").exists():
            continue
        print(f"  dropping container directory: {container.name}/", file=sys.stderr)
        shutil.rmtree(container)


def build_vendored_plugin(plugin: dict, upstream: dict) -> None:
    """Copy a complete upstream plugin into plugins/<name>/, generate plugin.json."""
    name = plugin["name"]
    submodule_path = REPO_ROOT / upstream["submodule"]
    plugin_dir = PLUGINS_DIR / name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # Copy skills and commands wholesale if they exist upstream.
    for subdir in ("skills", "commands", "agents", "hooks"):
        src = submodule_path / subdir
        if src.is_dir():
            shutil.copytree(src, plugin_dir / subdir)

    skills_root_dir = plugin_dir / "skills"
    drop_non_skill_containers(skills_root_dir)

    # Inject the `via galeep` vendor author into every copied SKILL.md.
    attribute_skill_tree(skills_root_dir, upstream.get("author"))

    # If upstream has .mcp.json or .lsp.json at root, copy those too.
    for mcp_file in (".mcp.json", ".lsp.json"):
        src = submodule_path / mcp_file
        if src.is_file():
            shutil.copy2(src, plugin_dir / mcp_file)

    # Generate plugin.json — pull metadata from upstream marketplace.json if present.
    upstream_marketplace = submodule_path / ".claude-plugin" / "marketplace.json"
    description = plugin["description"]
    version = "0.1.0"
    if upstream_marketplace.exists():
        try:
            data = json.loads(upstream_marketplace.read_text())
            version = data.get("metadata", {}).get("version", version)
        except Exception:
            pass

    write_json(
        plugin_dir / ".claude-plugin" / "plugin.json",
        {
            "name": name,
            "version": version,
            "description": description,
            "author": {"name": "K-Dense Inc.", "email": "contact@k-dense.ai"},
            "homepage": f"https://github.com/{upstream['upstream_repo']}",
            "license": upstream["license"],
        },
    )

    plugin_dir.joinpath("README.md").write_text(
        f"""# {name}

{description}

## Provenance

Vendored from [{upstream['upstream_repo']}](https://github.com/{upstream['upstream_repo']}) @ `{upstream_version(upstream)}`.
Licensed under {upstream['license']}. All credit to K-Dense AI.

This plugin is generated by `scripts/build.sh` from `plugins.yaml`. Edits here will be overwritten on rebuild.
"""
    )


def build_vendored_whole_plugin(plugin: dict, upstream: dict) -> None:
    """Copy a complete upstream plugin whose layout does NOT match the simple
    skills-at-root shape build_vendored_plugin assumes.

    Unlike build_vendored_plugin, this PRESERVES the upstream
    .claude-plugin/plugin.json verbatim (it can wire hooks, MCP servers, etc.
    that a generated manifest would silently drop) and copies the plugin's own
    source tree (e.g. src/ that the hooks call). Used for caveman, whose repo
    root is the plugin and whose hooks live in src/hooks/ referenced from
    plugin.json.

    Only a curated set of TOP-LEVEL entries is copied. Platform-variant dirs
    (.codex, .junie, ...), dev tooling (tests, evals, benchmarks), and package
    metadata are intentionally excluded. Note `src/` is copied whole, so inert
    subtrees inside it (e.g. src/plugins/opencode, src/mcp-servers) ride along;
    they are not wired by the preserved plugin.json and are harmless, but the
    curation is top-level only, not recursive into src/.
    """
    name = plugin["name"]
    submodule_path = REPO_ROOT / upstream["submodule"]
    # Allow the plugin to live in a subdir of the submodule; default is root.
    src_root = submodule_path / upstream.get("plugin_root", ".")
    plugin_dir = PLUGINS_DIR / name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    copy_dirs = ("skills", "commands", "agents", "hooks", "src", "assets")
    # LICENSING.md / LICENSE.BSL: caveman v2.1.0 relicensed to a split model and
    # its root LICENSE now opens with a scope note naming both files. None of the
    # BSL-1.1 directories that note lists (engine/, proxy/, cacheengine/,
    # rewriter/, browse/, mcp/, shrink/, cavemem Go core, shared/platform/) are in
    # copy_dirs, so what we vendor is MIT — but shipping the scope note without
    # the documents it points at leaves a dangling reference in a license file.
    # Copied when present; absent upstream (or on an older pin) they are skipped.
    copy_files = ("LICENSE", "LICENSING.md", "LICENSE.BSL")
    for d in copy_dirs:
        s = src_root / d
        if s.is_dir():
            shutil.copytree(s, plugin_dir / d)
    for f in copy_files:
        s = src_root / f
        if s.is_file():
            shutil.copy2(s, plugin_dir / f)

    # Same non-skill container drop the `vendored` path does: caveman v2.1.0
    # added skills/generated/, which has no SKILL.md and fails validation.
    drop_non_skill_containers(plugin_dir / "skills")

    # Inject the `via galeep` vendor author into every copied SKILL.md. Runs
    # before apply_downstream_patches (in main); patch anchors live in hook src/
    # and skill bodies, never the frontmatter name/author region, so this is safe.
    attribute_skill_tree(plugin_dir / "skills", upstream.get("author"))

    # Preserve the upstream manifest verbatim (NOT regenerated) so its hooks/MCP
    # wiring survives. Copy only plugin.json out of .claude-plugin/ — the
    # upstream marketplace.json must not leak into the plugin dir.
    upstream_manifest = src_root / ".claude-plugin" / "plugin.json"
    if not upstream_manifest.is_file():
        raise SystemExit(
            f"vendored-whole plugin {name!r}: no .claude-plugin/plugin.json at "
            f"{src_root} — cannot preserve manifest"
        )
    manifest = json.loads(upstream_manifest.read_text())
    # Backfill a semver version if upstream omits one (validate-plugin.sh warns
    # otherwise). Derive from the pinned tag (vX.Y.Z -> X.Y.Z).
    manifest.setdefault("version", upstream_version(upstream).lstrip("v"))
    write_json(plugin_dir / ".claude-plugin" / "plugin.json", manifest)

    plugin_dir.joinpath("README.md").write_text(
        f"""# {name}

{plugin["description"]}

## Provenance

Vendored whole from [{upstream['upstream_repo']}](https://github.com/{upstream['upstream_repo']}) @ `{upstream_version(upstream)}`.
Licensed under {upstream['license']}. All credit to the upstream author.

Downstream edits (if any) are applied from `patches/{name}.json` on every build
and fail the build if an anchor no longer matches upstream. This directory is
generated by `scripts/build.sh`; edit `patches/{name}.json`, not these files.
"""
    )


def apply_downstream_patches(plugin_name: str, required: bool = False) -> int:
    """Apply patches/<plugin_name>.json to the freshly built plugin tree.

    Each edit is an exact-substring find/replace (the same idiom the upstream
    sync workflow uses to bump plugins.yaml). The anchor MUST occur exactly
    once or the build aborts: a missing anchor means upstream changed the
    patched region (drift we must review and re-derive), and a duplicate anchor
    means the edit is ambiguous. Either way a guessed change is never applied
    silently.

    Fail-loud is the whole point, so every way the patch layer could quietly
    do nothing is also an abort: a declared-but-missing patch file (`required`),
    malformed JSON, a missing/typo'd "edits" key, a missing per-edit key, and a
    patch file that yields zero applied edits.

    HARD INVARIANT: this runs on a PRISTINE tree (clean_built_plugins wiped it,
    the build recopied upstream, then we patch). It is NOT re-entrant — an
    anchor that is a substring of its own replacement would duplicate content on
    a second pass, so we abort if the replacement text is already present.

    Returns the number of edits applied (0 only when no patch file exists and
    the plugin did not declare one).
    """
    patch_file = PATCHES_DIR / f"{plugin_name}.json"
    if not patch_file.exists():
        if required:
            raise SystemExit(
                f"patch {plugin_name}: plugins.yaml sets `patched: true` but "
                f"{patch_file} is missing — refusing to publish an unpatched plugin"
            )
        return 0

    try:
        spec = json.loads(patch_file.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"patch {plugin_name}: malformed JSON in {patch_file}: {e}")

    if not isinstance(spec.get("edits"), list):
        raise SystemExit(
            f'patch {plugin_name}: {patch_file} has no "edits" list '
            f"(a typo'd key would otherwise silently apply nothing)"
        )

    plugin_dir = PLUGINS_DIR / plugin_name
    applied = 0
    for i, edit in enumerate(spec["edits"]):
        for key in ("file", "find", "replace"):
            if key not in edit:
                raise SystemExit(
                    f"patch {plugin_name} edit #{i}: missing required key {key!r}"
                )
        find = edit["find"]
        replace = edit["replace"]
        if not isinstance(find, str) or not find:
            raise SystemExit(
                f"patch {plugin_name} edit #{i}: 'find' must be a non-empty string"
            )
        if not isinstance(replace, str):
            raise SystemExit(
                f"patch {plugin_name} edit #{i}: 'replace' must be a string"
            )
        rel = edit["file"]
        target = plugin_dir / rel
        if not target.is_file():
            raise SystemExit(
                f"patch {plugin_name} edit #{i}: target file not found: {rel}"
            )

        content = target.read_text()
        # Re-entrancy guard, scoped to INSERTION edits (the anchor is preserved
        # inside its own replacement). For those a completed apply leaves both
        # find and replace present, so count(find) can't tell pristine from
        # already-applied and the replace-present check disambiguates.
        # Non-insertion edits consume their anchor, so a re-run drift-aborts on
        # its own; we skip the check for them to avoid a false abort when the
        # replacement text legitimately recurs elsewhere in the file.
        if find in replace and replace in content:
            raise SystemExit(
                f"patch {plugin_name} edit #{i}: replacement already present in "
                f"{rel} — non-pristine tree (patches must run on a fresh build)"
            )
        occurrences = content.count(find)
        if occurrences == 0:
            raise SystemExit(
                f"patch {plugin_name} edit #{i}: DRIFT — anchor not found in {rel} "
                f"(upstream likely changed it). Re-derive the patch. "
                f"Anchor starts: {find[:70]!r}"
            )
        if occurrences > 1 and not edit.get("all", False):
            raise SystemExit(
                f"patch {plugin_name} edit #{i}: AMBIGUOUS — anchor occurs "
                f'{occurrences}x in {rel}; make it unique or set "all": true. '
                f"Anchor starts: {find[:70]!r}"
            )
        target.write_text(content.replace(find, replace))
        applied += 1

    if applied == 0:
        raise SystemExit(
            f"patch {plugin_name}: {patch_file} present but applied 0 edits "
            f"— refusing a silent no-op patch layer"
        )
    return applied


def build_marketplace(config: dict) -> None:
    entries = []
    for plugin in config["plugins"]:
        entry = {
            "name": plugin["name"],
            "description": plugin["description"],
            "source": f"./plugins/{plugin['name']}",
        }
        if "category" in plugin:
            entry["category"] = plugin["category"]
        entries.append(entry)

    market = config["marketplace"]
    output = {
        "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
        "name": market["name"],
        "version": market.get("version", "0.1.0"),
        "description": market["description"],
        "owner": market["owner"],
        "plugins": entries,
    }
    if "homepage" in market:
        output["metadata"] = {"homepage": market["homepage"]}
    write_json(MARKETPLACE_JSON, output)


def write_provenance_sidecar(config: dict) -> None:
    """Write a small JSON file recording exactly which upstream commits we built from.
    CI compares this to detect drift."""
    upstreams = {}
    for name, up in config["upstreams"].items():
        submodule_path = REPO_ROOT / up["submodule"]
        upstreams[name] = {
            "version": upstream_version(up),
            "sha": submodule_sha(submodule_path),
            "describe": submodule_describe(submodule_path),
            "repo": up["upstream_repo"],
        }
    write_json(REPO_ROOT / ".claude-plugin" / "provenance.json", upstreams)


def warn_license_drift(config) -> None:
    """Advisory notice when an upstream's licensing documents no longer match the
    fingerprint recorded in plugins.yaml.

    NOT the patch-anchor idiom, deliberately. A drifted anchor aborts the build
    because the OUTPUT would be wrong; a changed license leaves the output fine
    and a DECLARATION possibly stale. Aborting here would let any upstream
    copyright-year edit turn the nightly red and suppress that day's sync PR —
    trading a silent relicense for a silent sync outage, the worse failure for a
    workflow whose job is telling a human that third-party code moved.

    The durable signal is the sync PR body (see .github/workflows/sync-upstream.yml);
    this is the local-build echo of it. Run `scripts/license-fingerprint.py --write`
    to record reviewed terms.
    """
    stale = [
        (name, up.get("license_fingerprint"), licenses.fingerprint_docs(REPO_ROOT / up["submodule"]))
        for name, up in config["upstreams"].items()
    ]
    stale = [row for row in stale if row[1] != row[2]]
    if not stale:
        return
    for name, recorded, actual in stale:
        was = "unrecorded" if recorded is None else recorded[:12]
        # `::warning::` renders as an annotation in GitHub Actions and as plain
        # text everywhere else, so one line serves both.
        print(
            f"::warning::license drift: upstream {name!r} licensing documents "
            f"changed ({was} -> {actual[:12]}). Review terms, then run "
            f"scripts/license-fingerprint.py --write",
            file=sys.stderr,
        )


def main():
    config = yaml.safe_load(PLUGINS_YAML.read_text())

    # Advisory only — never aborts. See warn_license_drift's docstring for why
    # this does not use the fail-closed idiom the patch anchors use.
    warn_license_drift(config)

    # Load locked assignment tables and run the coverage gate BEFORE building
    # anything: every present upstream item must map to a declared plugin, and
    # the tables must carry no stale entries. A gate failure here is a real
    # error (fix the table, not silence it).
    skills_table = tables.load_table(REPO_ROOT / "taxonomy" / "skills.yaml")
    agents_table = tables.load_table(REPO_ROOT / "taxonomy" / "agents.yaml")
    declared = {p["name"] for p in config["plugins"]}

    sk_up = config["upstreams"]["scientific-agent-skills"]
    skills_present = {
        d.name for d in (REPO_ROOT / sk_up["submodule"] / sk_up["skills_root"]).iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }
    tables.coverage_gate(skills_present, skills_table, declared, "skill")

    ag_up = config["upstreams"]["scientific-agents"]
    catalog = json.loads(
        (REPO_ROOT / ag_up["submodule"] / ag_up["catalog"]).read_text()
    )["agents"]
    agents_present = {a["slug"] for a in catalog}
    tables.coverage_gate(agents_present, agents_table, declared, "agent")
    catalog_by_slug = {a["slug"]: a for a in catalog}

    clean_built_plugins()

    built = vendored = vendored_whole = agents_built = 0
    for plugin in config["plugins"]:
        kind = plugin["kind"]
        upstream_name = plugin.get("upstream")
        if kind in ("built", "vendored", "vendored-whole", "agents"):
            if upstream_name not in config["upstreams"]:
                raise SystemExit(
                    f"plugin {plugin['name']} references unknown upstream {upstream_name!r}"
                )
            upstream = config["upstreams"][upstream_name]

        if kind == "built":
            build_built_plugin(plugin, upstream, skills_table)
            built += 1
        elif kind == "vendored":
            build_vendored_plugin(plugin, upstream)
            vendored += 1
        elif kind == "vendored-whole":
            build_vendored_whole_plugin(plugin, upstream)
            vendored_whole += 1
        elif kind == "agents":
            build_agents_plugin(plugin, upstream, agents_table, catalog_by_slug)
            agents_built += 1
        elif kind == "local":
            # local plugins live untouched in plugins/<name>/ already
            pass
        else:
            raise SystemExit(f"unknown plugin kind: {kind!r}")

    # Apply downstream patches AFTER every plugin tree is in place. The tree was
    # just recopied pristine from upstream (clean_built_plugins wiped it first),
    # so re-applying here is idempotent. A missing or non-unique anchor aborts
    # the build: upstream drift is surfaced, never silently absorbed.
    patched_files = 0
    for plugin in config["plugins"]:
        patched_files += apply_downstream_patches(
            plugin["name"], required=plugin.get("patched", False)
        )

    build_marketplace(config)
    write_provenance_sidecar(config)

    print(
        f"render.py: built={built} vendored={vendored} "
        f"vendored-whole={vendored_whole} agents={agents_built} "
        f"patched-edits={patched_files} total={len(config['plugins'])}"
    )


if __name__ == "__main__":
    main()
