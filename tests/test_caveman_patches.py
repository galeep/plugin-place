import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "plugins" / "caveman" / "src" / "hooks"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="hooks require node")


@pytest.fixture
def env(tmp_path):
    env = os.environ.copy()
    for key in ("CAVEMAN_REINFORCE", "CAVEMAN_DEFAULT_MODE", "CLAUDE_PLUGIN_ROOT"):
        env.pop(key, None)
    env.update(HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path),
               CLAUDE_CONFIG_DIR=str(tmp_path))
    (tmp_path / ".caveman-active").write_text("caveman")
    return env


def run_hook(hook, env, prompt="hello"):
    result = subprocess.run(
        ["node", str(hook)], input=json.dumps({"prompt": prompt, "cwd": env["HOME"]}),
        text=True, capture_output=True, env=env, check=True,
    )
    return result.stdout


def test_reminder_preserves_upstream_guidance_and_opt_out(env):
    hook = HOOKS / "caveman-mode-tracker.js"
    text = json.loads(run_hook(hook, env))["hookSpecificOutput"]["additionalContext"]
    assert "Answer only what was asked" in text
    assert "FLOOR for low-value turns" in text
    assert "never the reasoning" in text
    env["CAVEMAN_REINFORCE"] = "0"
    assert run_hook(hook, env) == ""


@pytest.mark.parametrize("old_config", [False, True])
def test_session_start_fallback_without_skills(tmp_path, env, old_config):
    hooks = tmp_path / "hooks"
    shutil.copytree(HOOKS, hooks)
    if old_config:
        with (hooks / "caveman-config.js").open("a") as config:
            config.write("\nmodule.exports.fallbackRuleset = undefined;\n")
    text = run_hook(hooks / "caveman-activate.js", env)
    assert "Terseness is the floor for low-value turns" in text
    assert "9. Never perform caveman." in text


def test_switch_uses_shared_fallback_with_reinforcement_disabled(tmp_path, env):
    hooks = tmp_path / "hooks"
    shutil.copytree(HOOKS, hooks)
    env["CAVEMAN_REINFORCE"] = "0"
    text = json.loads(run_hook(hooks / "caveman-mode-tracker.js", env, "/ultracave"))
    context = text["hookSpecificOutput"]["additionalContext"]
    assert "Terseness is the floor for low-value turns" in context
    assert "9. Never perform caveman." in context
    assert "FLOOR for low-value turns" not in context
