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
