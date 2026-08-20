"""The pull-request version bump must discriminate, not merely run.

A plugin change that merges without a version bump reaches no installed copy:
the installer caches under ``<name>/<version>/``, so ``/reload-plugins`` reports
success and loads the old code. PR #77 shipped that way. These cases pin what
the bump touches and, as importantly, what it refuses to touch.
"""

import json
import os
import subprocess
import sys

import pytest
import yaml

from scripts.lib import plugin_versions as pv

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOCAL = {"laconic"}


def versions(mapping):
    """A version lookup over a plain dict; a missing key means no manifest."""
    return lambda name: mapping.get(name)


def manifest(version="0.2.0", name="laconic"):
    return json.dumps({"name": name, "description": "x", "version": version}, indent=2) + "\n"


# ── the core discrimination ──────────────────────────────────────────────────


def test_a_changed_local_plugin_with_no_version_change_is_planned():
    bumps, _ = pv.plan(
        ["plugins/laconic/src/hooks/laconic-mode-tracker.js"],
        LOCAL,
        versions({"laconic": "0.2.0"}),
        versions({"laconic": "0.2.0"}),
    )
    assert [b.plugin for b in bumps] == ["laconic"]
    assert (bumps[0].old, bumps[0].new) == ("0.2.0", "0.2.1")
    assert bumps[0].manifest == "plugins/laconic/.claude-plugin/plugin.json"


def test_a_plugin_the_author_already_bumped_is_left_alone():
    """The bump must not fight an author who bumped the minor for new behaviour."""
    bumps, skips = pv.plan(
        ["plugins/laconic/src/hooks/laconic-mode-tracker.js"],
        LOCAL,
        versions({"laconic": "0.2.0"}),
        versions({"laconic": "0.3.0"}),
    )
    assert bumps == []
    assert [s.plugin for s in skips] == ["laconic"]
    assert "already bumped" in skips[0].reason


def test_a_change_outside_plugins_is_ignored():
    bumps, skips = pv.plan(
        ["scripts/render.py", "README.md", ".github/workflows/ci.yml", "plugins.yaml"],
        LOCAL,
        versions({"laconic": "0.2.0"}),
        versions({"laconic": "0.2.0"}),
    )
    assert (bumps, skips) == ([], [])


def test_every_offending_plugin_is_named_in_one_run():
    bumps, _ = pv.plan(
        ["plugins/laconic/README.md", "plugins/other-local/commands/go.md"],
        {"laconic", "other-local"},
        versions({"laconic": "0.2.0", "other-local": "1.4.9"}),
        versions({"laconic": "0.2.0", "other-local": "1.4.9"}),
    )
    assert [(b.plugin, b.new) for b in bumps] == [("laconic", "0.2.1"), ("other-local", "1.4.10")]


# ── the two exemption decisions ──────────────────────────────────────────────


def test_a_generated_plugin_is_excluded_even_when_its_files_change():
    """Vendored and built plugins are render.py output, so their version is not ours.

    ``built``/``agents`` hardcode 0.1.0, ``vendored`` reads upstream metadata,
    ``vendored-whole`` derives from the pinned tag. A bump written here would be
    erased by the next build.sh and would fail CI's build-drift step. It also
    keeps this off sync-upstream.yml's territory entirely.
    """
    bumps, skips = pv.plan(
        [
            "plugins/caveman/src/hooks/per-turn.js",
            "plugins/sci-physics-astronomy/skills/x/SKILL.md",
        ],
        LOCAL,
        versions({"caveman": "2.1.0", "sci-physics-astronomy": "0.1.0"}),
        versions({"caveman": "2.1.0", "sci-physics-astronomy": "0.1.0"}),
    )
    assert bumps == []
    assert [s.plugin for s in skips] == ["caveman", "sci-physics-astronomy"]
    assert all("generated" in s.reason for s in skips)


def test_a_docs_only_change_inside_a_local_plugin_still_bumps():
    """No docs exemption: a README is copied into the installed plugin too."""
    bumps, _ = pv.plan(
        ["plugins/laconic/README.md"],
        LOCAL,
        versions({"laconic": "0.2.0"}),
        versions({"laconic": "0.2.0"}),
    )
    assert [b.plugin for b in bumps] == ["laconic"]


def test_the_repos_own_plugins_yaml_marks_only_laconic_local():
    """Grounds the exclusion in the real manifest rather than a fixture."""
    with open(os.path.join(REPO, "plugins.yaml")) as f:
        config = yaml.safe_load(f)
    names = pv.local_plugin_names(config)
    assert "laconic" in names
    assert names.isdisjoint({"caveman", "claude-scientific-writer", "sci-physics-astronomy"})


# ── the shapes that must not crash or guess ──────────────────────────────────


def test_a_plugin_added_by_this_pr_is_skipped():
    bumps, skips = pv.plan(
        ["plugins/newbie/.claude-plugin/plugin.json"],
        {"newbie"},
        versions({}),
        versions({"newbie": "0.1.0"}),
    )
    assert bumps == []
    assert "new plugin" in skips[0].reason


def test_a_plugin_deleted_by_this_pr_is_skipped():
    bumps, skips = pv.plan(
        ["plugins/laconic/README.md"],
        LOCAL,
        versions({"laconic": "0.2.0"}),
        versions({}),
    )
    assert bumps == []
    assert "removed" in skips[0].reason


def test_a_local_plugin_with_no_version_field_fails_loudly():
    with pytest.raises(pv.VersionError) as e:
        pv.read_version(json.dumps({"name": "laconic"}), "plugins/laconic/.claude-plugin/plugin.json")
    assert "plugins/laconic/.claude-plugin/plugin.json" in str(e.value)
    assert "version" in str(e.value)


@pytest.mark.parametrize(
    "text", ["[]", '"laconic"', "42", "null", "true", '[{"version": "1.0.0"}]']
)
def test_a_manifest_that_is_valid_json_but_not_an_object_fails_loudly(text):
    """The JSON half of the plugins.yaml shape check, and the last of that family.

    `json.loads` accepts any JSON value, so a manifest holding a list or a
    scalar parsed fine and then met `.get`, raising AttributeError past the
    VersionError handling. main() would have exited 1, which the fork job shows
    a contributor as the gate rather than as the tool failing. Issue #79.
    """
    with pytest.raises(pv.VersionError) as e:
        pv.read_version(text, "plugins/laconic/.claude-plugin/plugin.json")
    assert "plugins/laconic/.claude-plugin/plugin.json" in str(e.value)


def test_an_ordinary_manifest_object_is_still_read_normally():
    """The guard must not cost the ordinary case."""
    assert pv.read_version(manifest("1.2.3"), "m.json") == "1.2.3"


def test_a_manifest_that_is_not_an_object_exits_as_a_tool_error(tmp_path):
    """End to end: exit 2, not the exit 1 the fork job reads as the gate."""
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins/laconic/.claude-plugin/plugin.json").write_text('["laconic"]\n')
    run("commit", "-q", "-am", "manifest is a list")

    result = cli(root, "--check")
    assert result.returncode == 2
    assert "plugins/laconic/.claude-plugin/plugin.json" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_non_semver_version_is_not_guessed_at():
    with pytest.raises(pv.VersionError) as e:
        pv.bump_patch("0.2", "plugins/laconic/.claude-plugin/plugin.json")
    assert "plugins/laconic/.claude-plugin/plugin.json" in str(e.value)


def test_the_bump_rewrites_one_field_and_nothing_else():
    before = manifest("0.2.0")
    after = pv.rewrite_version(before, "0.2.0", "0.2.1", "m.json")
    assert json.loads(after)["version"] == "0.2.1"
    assert after == before.replace('"version": "0.2.0"', '"version": "0.2.1"')


# ── against a real git repository ────────────────────────────────────────────


def make_repo(root, version="0.2.0"):
    def run(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    plugin = root / "plugins" / "laconic" / ".claude-plugin"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(manifest(version))
    (root / "plugins" / "laconic" / "README.md").write_text("# laconic\n")
    (root / "plugins" / "caveman" / ".claude-plugin").mkdir(parents=True)
    (root / "plugins" / "caveman" / ".claude-plugin" / "plugin.json").write_text(
        manifest("2.1.0", "caveman")
    )
    other = root / "plugins" / "other-local" / ".claude-plugin"
    other.mkdir(parents=True)
    (other / "plugin.json").write_text(manifest("1.0.0", "other-local"))
    (root / "plugins" / "other-local" / "note.md").write_text("shared\n")
    (root / "plugins.yaml").write_text(
        yaml.safe_dump(
            {"plugins": [{"name": "laconic", "kind": "local"},
                         {"name": "other-local", "kind": "local"},
                         {"name": "caveman", "kind": "vendored-whole"}]}
        )
    )
    run("init", "-q", "-b", "main")
    run("config", "user.email", "test@example.invalid")
    run("config", "user.name", "test")
    run("add", "-A")
    run("commit", "-q", "-m", "base")
    run("checkout", "-q", "-b", "fix")
    return run


def cli(root, *args):
    return subprocess.run(
        [sys.executable, os.path.join(REPO, "scripts", "bump-plugin-versions.py"),
         "--repo", str(root), "--base-ref", "main", *args],
        capture_output=True, text=True,
    )


def test_apply_bumps_a_real_branch_and_a_second_run_finds_nothing_to_do(tmp_path):
    """The loop proof: the workflow pushes to the PR branch, which can retrigger it.

    The second run must see the version it already wrote and exit cleanly with
    no further change, or the workflow would bump on every retrigger forever.
    """
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins" / "laconic" / "README.md").write_text("# laconic\n\nnew line\n")
    run("commit", "-q", "-am", "docs")

    first = cli(root, "--apply")
    assert first.returncode == 0, first.stderr
    assert "bumped laconic: 0.2.0 -> 0.2.1" in first.stdout
    written = json.loads((root / "plugins/laconic/.claude-plugin/plugin.json").read_text())
    assert written["version"] == "0.2.1"

    run("commit", "-q", "-am", "chore: bump")
    second = cli(root, "--apply")
    assert second.returncode == 0, second.stderr
    assert "no plugin needs a version bump" in second.stdout
    assert "bumped" not in second.stdout
    unchanged = json.loads((root / "plugins/laconic/.claude-plugin/plugin.json").read_text())
    assert unchanged["version"] == "0.2.1"


def test_check_mode_fails_naming_the_file_and_writes_nothing(tmp_path):
    """The fork path: no push is possible, so say what to edit and fail."""
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins" / "laconic" / "README.md").write_text("# laconic\n\nnew line\n")
    run("commit", "-q", "-am", "docs")

    result = cli(root, "--check")
    assert result.returncode == 1
    assert "plugins/laconic/.claude-plugin/plugin.json" in result.stdout
    assert "minor" in result.stdout and "patch" in result.stdout
    still = json.loads((root / "plugins/laconic/.claude-plugin/plugin.json").read_text())
    assert still["version"] == "0.2.0"


def test_a_generated_plugin_changed_on_a_real_branch_is_not_touched(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins" / "caveman" / "note.md").write_text("upstream\n")
    run("add", "-A")
    run("commit", "-q", "-m", "vendored change")

    result = cli(root, "--apply")
    assert result.returncode == 0, result.stderr
    assert "no plugin needs a version bump" in result.stdout
    assert "caveman left alone" in result.stderr
    kept = json.loads((root / "plugins/caveman/.claude-plugin/plugin.json").read_text())
    assert kept["version"] == "2.1.0"


def test_a_file_moved_between_plugins_bumps_both_ends(tmp_path):
    """Rename detection would name only the destination.

    The plugin that lost the file still ships it in every installed copy, so it
    needs a bump just as much as the one that gained it.
    """
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins" / "other-local" / "note.md").rename(
        root / "plugins" / "laconic" / "note.md"
    )
    run("add", "-A")
    run("commit", "-q", "-m", "move a file between plugins")

    result = cli(root, "--apply")
    assert result.returncode == 0, result.stderr
    assert "bumped laconic: 0.2.0 -> 0.2.1" in result.stdout
    assert "bumped other-local: 1.0.0 -> 1.0.1" in result.stdout


def test_a_plugin_created_by_this_pr_is_not_bumped_on_a_real_branch(tmp_path):
    """Nothing installed can be stale for a plugin that did not exist before."""
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    newbie = root / "plugins" / "newbie" / ".claude-plugin"
    newbie.mkdir(parents=True)
    (newbie / "plugin.json").write_text(manifest("0.1.0", "newbie"))
    (root / "plugins.yaml").write_text(
        yaml.safe_dump(
            {"plugins": [{"name": "laconic", "kind": "local"},
                         {"name": "other-local", "kind": "local"},
                         {"name": "newbie", "kind": "local"},
                         {"name": "caveman", "kind": "vendored-whole"}]}
        )
    )
    run("add", "-A")
    run("commit", "-q", "-m", "add a plugin")

    result = cli(root, "--apply")
    assert result.returncode == 0, result.stderr
    assert "no plugin needs a version bump" in result.stdout
    assert "new plugin" in result.stderr
    assert json.loads((newbie / "plugin.json").read_text())["version"] == "0.1.0"


def test_a_broken_plugins_yaml_exits_as_a_tool_error_not_as_the_gate(tmp_path):
    """Exit 1 means "bump this"; a tool failure must not borrow that signal.

    The fork job branches on the exit code, so a crash that exited 1 would tell
    a contributor to bump a plugin the tool never managed to name.
    """
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins" / "laconic" / "README.md").write_text("# laconic\n\nnew\n")
    (root / "plugins.yaml").write_text("plugins: [oops\n")
    run("commit", "-q", "-am", "break the manifest")

    result = cli(root, "--check")
    assert result.returncode == 2
    assert "plugins.yaml" in result.stderr


def test_a_plugins_yaml_that_is_not_a_mapping_exits_as_a_tool_error(tmp_path):
    """Valid YAML of the wrong shape is still a tool error, not a stack trace.

    A top-level list parses fine, so the read succeeds and the shape check is
    the only thing standing between it and an AttributeError that would escape
    the VersionError handling in main() and lose the exit-2 contract.
    """
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins" / "laconic" / "README.md").write_text("# laconic\n\nnew\n")
    (root / "plugins.yaml").write_text("- name: laconic\n  kind: local\n")
    run("commit", "-q", "-am", "top-level list")

    result = cli(root, "--check")
    assert result.returncode == 2
    assert "plugins.yaml" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("config", [[], "", 0, False, ["laconic"], "laconic", 3])
def test_local_plugin_names_refuses_anything_but_a_mapping(config):
    """Including the falsy ones: an empty list must not read as no local plugins."""
    with pytest.raises(pv.VersionError) as e:
        pv.local_plugin_names(config)
    assert "plugins.yaml" in str(e.value)


# ── a manifest that cannot name the local plugins says so, never guesses ─────
#
# Each shape below used to reach `return set()` or leak an exception past the
# VersionError handling. Both read as "this repo has no local plugins", which is
# the silent under-bump the tool exists to stop: every plugin then looks
# generated and nothing is bumped. A leak is worse still in --check, where the
# exit code lands on 1 and tells a contributor to bump a plugin nothing named.


@pytest.mark.parametrize("plugins", [{"laconic": {"kind": "local"}}, "laconic", 42, True])
def test_a_plugins_key_that_is_not_a_list_is_refused(plugins):
    with pytest.raises(pv.VersionError) as e:
        pv.local_plugin_names({"plugins": plugins})
    assert "plugins.yaml" in str(e.value)


@pytest.mark.parametrize("entry", ["laconic", ["laconic"], 3, None])
def test_a_plugins_entry_that_is_not_a_mapping_is_refused(entry):
    with pytest.raises(pv.VersionError) as e:
        pv.local_plugin_names({"plugins": [entry]})
    assert "plugins.yaml" in str(e.value)


def test_a_plugins_yaml_with_no_plugins_key_at_all_is_refused():
    """Absence reads as "no local plugins" exactly as a wrong type does, so it fails too."""
    with pytest.raises(pv.VersionError) as e:
        pv.local_plugin_names({"marketplace": {"name": "plugin-place"}})
    assert "plugins.yaml" in str(e.value)


@pytest.mark.parametrize("name", [123, 1.5, True, ["laconic"], {"laconic": 1}, None, ""])
def test_a_local_entry_whose_name_is_not_a_usable_string_is_refused(name):
    """`name: 123` is an int in YAML, and plan() matches names as strings.

    A non-string name lands in the set without matching anything plugins_touched
    produces, so the plugin it names is skipped as generated and never bumped.
    """
    with pytest.raises(pv.VersionError) as e:
        pv.local_plugin_names({"plugins": [{"kind": "local", "name": name}]})
    assert "plugins.yaml" in str(e.value)


def test_a_digit_named_plugin_is_fine_when_quoted():
    """The type check must not cost a legal name: `name: "123"` is a real directory.

    This is the pair to the case above. An int is refused because plan() would
    never match it; the same characters as a string match and bump normally.
    """
    names = pv.local_plugin_names({"plugins": [{"kind": "local", "name": "123"}]})
    assert names == {"123"}
    bumps, _ = pv.plan(
        ["plugins/123/README.md"], names, versions({"123": "0.2.0"}), versions({"123": "0.2.0"})
    )
    assert [(b.plugin, b.new) for b in bumps] == [("123", "0.2.1")]


def test_an_empty_plugins_key_is_a_legitimate_empty_list():
    """`plugins:` with nothing under it declares no plugins; that is not malformed."""
    assert pv.local_plugin_names({"plugins": None}) == set()
    assert pv.local_plugin_names({"plugins": []}) == set()


UNDECODABLE = b'{"name": "laconic", "version": "0.\xff\xfe2.0"}'


def test_an_undecodable_plugins_yaml_is_a_version_error(tmp_path):
    """UnicodeDecodeError is a ValueError, so the OSError/YAMLError catch missed it."""
    (tmp_path / "plugins.yaml").write_bytes(b"plugins:\n  - name: \xff\xfe\n")
    with pytest.raises(pv.VersionError):
        pv.load_local_names(tmp_path)


def test_an_undecodable_manifest_in_the_worktree_is_a_version_error(tmp_path):
    manifest_dir = tmp_path / "plugins" / "laconic" / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_bytes(UNDECODABLE)
    with pytest.raises(pv.VersionError) as e:
        pv.version_reader_worktree(tmp_path)("laconic")
    assert "plugins/laconic/.claude-plugin/plugin.json" in str(e.value)


def test_an_undecodable_manifest_at_a_ref_is_a_version_error(tmp_path):
    """The git layer decodes its own output, so the base-ref read leaks the same way."""
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins/laconic/.claude-plugin/plugin.json").write_bytes(UNDECODABLE)
    run("commit", "-q", "-am", "bad bytes")
    with pytest.raises(pv.VersionError):
        pv.version_reader_at(root, "HEAD")("laconic")


def test_apply_bumps_turns_a_read_failure_into_a_version_error(tmp_path):
    manifest_dir = tmp_path / "plugins" / "laconic" / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_bytes(UNDECODABLE)
    bump = pv.Bump("laconic", "plugins/laconic/.claude-plugin/plugin.json", "0.2.0", "0.2.1")
    with pytest.raises(pv.VersionError) as e:
        pv.apply_bumps([bump], tmp_path)
    assert "plugins/laconic/.claude-plugin/plugin.json" in str(e.value)


def test_a_plugins_list_of_the_wrong_shape_exits_as_a_tool_error(tmp_path):
    """The end-to-end contract for the fork job: exit 2, not the exit 1 gate."""
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins" / "laconic" / "README.md").write_text("# laconic\n\nnew\n")
    (root / "plugins.yaml").write_text("plugins:\n  laconic:\n    kind: local\n")
    run("commit", "-q", "-am", "plugins as a mapping")

    result = cli(root, "--check")
    assert result.returncode == 2
    assert "plugins.yaml" in result.stderr
    assert "Traceback" not in result.stderr


def test_an_undecodable_manifest_exits_as_a_tool_error_not_as_the_gate(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run = make_repo(root)
    (root / "plugins/laconic/.claude-plugin/plugin.json").write_bytes(UNDECODABLE)
    run("commit", "-q", "-am", "bad bytes")

    result = cli(root, "--check")
    assert result.returncode == 2
    assert "plugins/laconic/.claude-plugin/plugin.json" in result.stderr
    assert "Traceback" not in result.stderr
