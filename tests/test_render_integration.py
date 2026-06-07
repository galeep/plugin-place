import subprocess, sys, json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

def test_build_runs_and_emits_agent_plugin():
    r = subprocess.run([sys.executable, "scripts/render.py"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
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
