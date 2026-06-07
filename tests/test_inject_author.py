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

def test_yaml_dq_escapes_newline():
    assert fm.yaml_dq("line1\nline2") == '"line1\\nline2"'

def test_inject_raises_without_frontmatter():
    import pytest
    with pytest.raises(ValueError):
        fm.inject_author("no frontmatter\n", "x")

EXISTING_AUTHOR = (
    "---\n"
    "name: adaptyv\n"
    'author: "K-Dense, Inc."\n'
    "description: x.\n"
    "metadata:\n"
    "  skill-author: K-Dense Inc.\n"
    "---\n"
    "body\n"
)

def test_inject_appends_mark_to_existing_author():
    out = fm.inject_author(EXISTING_AUTHOR, "ignored via galeep")
    head, _ = fm.split_frontmatter(out)
    assert fm.get_field(head, "author") == "K-Dense, Inc. via galeep"

def test_inject_idempotent_on_marked_existing_author():
    once = fm.inject_author(EXISTING_AUTHOR, "ignored via galeep")
    twice = fm.inject_author(once, "ignored2 via galeep")
    assert once == twice
    head, _ = fm.split_frontmatter(twice)
    assert sum(1 for l in head.splitlines() if l.startswith("author:")) == 1
