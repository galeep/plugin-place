from scripts.lib import attribution as attr

def test_skill_author_with_origin():
    assert attr.skill_author("K-Dense Inc.") == "K-Dense Inc. via galeep"
    assert attr.skill_author("Yaroslav Halchenko") == "Yaroslav Halchenko via galeep"

def test_skill_author_without_origin():
    assert attr.skill_author(None) == "via galeep"
    assert attr.skill_author("") == "via galeep"
    assert attr.skill_author("   ") == "via galeep"

def test_skill_author_uses_fallback_when_no_original():
    assert attr.skill_author(None, "Julius Brussee") == "Julius Brussee via galeep"
    assert attr.skill_author("", "K-Dense Inc.") == "K-Dense Inc. via galeep"

def test_skill_author_prefers_original_over_fallback():
    assert attr.skill_author("Real Author", "Fallback") == "Real Author via galeep"

def test_skill_author_bare_when_neither():
    assert attr.skill_author(None, None) == "via galeep"

def test_agent_author_constant():
    assert attr.AGENT_AUTHOR == "K-Dense, Inc. via galeep"
