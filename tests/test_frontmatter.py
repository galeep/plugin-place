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
