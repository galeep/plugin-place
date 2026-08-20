"""The laconic mode tracker must recognise a slash command.

Claude Code hands a UserPromptSubmit hook an envelope rather than the literal
command the user typed:

    <command-message>laconic</command-message>
    <command-name>/laconic:laconic</command-name>
    <command-args>laconic</command-args>

The name is namespaced as ``/laconic:laconic`` whenever a plugin and one of its
commands share a name. The tracker matched a literal ``/laconic`` only, so every
slash invocation was a silent no-op: no flag written, no reminder injected, and
the register looked installed but dead. These cases pin the shapes.
"""

import json
import os
import shutil
import subprocess
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "plugins", "laconic")
HOOK = os.path.join(PLUGIN, "src", "hooks", "laconic-mode-tracker.js")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="the hook is a node script"
)


def hermetic_env(config_dir):
    """The host environment must not decide what these tests observe.

    ``getActivationLevel`` consults ``LACONIC_DEFAULT_MODE`` and a config file
    found through ``XDG_CONFIG_HOME``, falling back to ``~/.config/laconic`` when
    that is unset, so a developer running with laconic configured would shift the
    cases that pass no argument. Point the config lookup at an empty directory
    and drop the overrides.
    """
    empty = os.path.join(str(config_dir), "empty-config-home")
    os.makedirs(empty, exist_ok=True)
    env = dict(os.environ)
    for name in ("LACONIC_DEFAULT_MODE", "LACONIC_DEBUG"):
        env.pop(name, None)
    env["XDG_CONFIG_HOME"] = empty
    env["APPDATA"] = empty
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    env["CLAUDE_PLUGIN_ROOT"] = PLUGIN
    return env


def run_hook(prompt, config_dir):
    payload = json.dumps({"prompt": prompt, "session_id": "test", "cwd": "/tmp"})
    env = hermetic_env(config_dir)
    proc = subprocess.run(
        ["node", HOOK], input=payload, capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, f"hooks must always exit 0, got {proc.returncode}"
    flag_path = os.path.join(str(config_dir), ".laconic-active")
    flag = None
    if os.path.exists(flag_path):
        with open(flag_path) as handle:
            flag = handle.read().strip()
    return flag, proc.stdout


def envelope(name, args=""):
    return (
        f"<command-message>laconic</command-message>\n"
        f"<command-name>{name}</command-name>\n"
        f"<command-args>{args}</command-args>"
    )


def envelope_without_args_tag(name):
    """Claude Code omits the tag entirely when a command is given no arguments."""
    return (
        f"<command-message>laconic</command-message>\n"
        f"<command-name>{name}</command-name>"
    )


@pytest.mark.parametrize(
    "name,args,expected",
    [
        ("/laconic:laconic", "laconic", "laconic"),
        ("/laconic", "laconic", "laconic"),
        ("/laconic:laconic", "", "laconic"),
        ("/laconic", "", "laconic"),
        ("/laconic:laconic", "off", "off"),
        ("/laconic", "off", "off"),
    ],
)
def test_envelope_switches_the_register(tmp_path, name, args, expected):
    flag, _ = run_hook(envelope(name, args), tmp_path)
    assert flag == expected


def test_activation_injects_the_reminder(tmp_path):
    _, stdout = run_hook(envelope("/laconic:laconic", "laconic"), tmp_path)
    assert "LACONIC REGISTER ACTIVE" in stdout


def test_a_foreign_command_cannot_switch_this_register(tmp_path):
    """Another command's arguments must not read as a request to turn us off."""
    flag, _ = run_hook(envelope("/caveman", "laconic off"), tmp_path)
    assert flag is None


def test_natural_language_still_deactivates(tmp_path):
    flag, _ = run_hook("please stop laconic", tmp_path)
    assert flag == "off"


@pytest.mark.parametrize("name", ["/laconic:laconic", "/laconic"])
def test_an_absent_command_args_tag_still_activates(tmp_path, name):
    """The reconstruction treats a missing tag as no arguments, same as an empty one."""
    flag, _ = run_hook(envelope_without_args_tag(name), tmp_path)
    assert flag == "laconic"
