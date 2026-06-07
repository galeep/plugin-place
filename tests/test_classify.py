from scripts.lib import classify

RULES = [
    ("physics-astro", r"physicist|astronom"),
    ("chemistry", r"chemist"),
    ("engineering", r"engineer"),
]

def test_first_match_wins():
    assert classify.classify_text("astrophysicist astronomer", RULES) == "physics-astro"

def test_later_rule_matches():
    assert classify.classify_text("organic chemist", RULES) == "chemistry"

def test_no_match_returns_none():
    assert classify.classify_text("philosopher", RULES) is None

def test_compile_rules_from_spec():
    spec = {"rules": [{"domain": "chemistry", "pattern": "chemist"}]}
    compiled = classify.compile_rules(spec)
    assert compiled[0][0] == "chemistry"
    assert classify.classify_text("a chemist", compiled) == "chemistry"

def test_overrides_take_precedence():
    spec = {
        "rules": [{"domain": "engineering", "pattern": "engineer"}],
        "overrides": {"chemical-engineer": "chemistry"},
    }
    compiled = classify.compile_rules(spec)
    assert classify.assign("chemical-engineer", "chemical engineer", "x", compiled, spec.get("overrides", {})) == "chemistry"
    assert classify.assign("civil-engineer", "civil engineer", "x", compiled, {}) == "engineering"
