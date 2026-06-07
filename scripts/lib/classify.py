"""Ordered keyword classifier used only by the seed generator (never the build).

A rules spec is `{"rules": [{"domain","pattern"}], "overrides": {slug: domain}}`.
"""
import re


def compile_rules(spec):
    """Return [(domain, compiled_regex), ...] in spec order."""
    return [(r["domain"], re.compile(r["pattern"])) for r in spec["rules"]]


def classify_text(haystack, rules):
    """First domain whose pattern matches `haystack`, else None. `rules` is a
    list of (domain, pattern) where pattern may be a raw string OR a compiled
    regex — `re.search` accepts both."""
    for domain, pattern in rules:
        if re.search(pattern, haystack):
            return domain
    return None


def assign(slug, profession, work_mode, compiled_rules, overrides):
    """Resolve a single item to a domain: override first, then rules over the
    lowercased slug+profession+work_mode haystack. None if nothing matches."""
    if slug in overrides:
        return overrides[slug]
    haystack = " ".join([slug, profession, work_mode]).lower()
    return classify_text(haystack, compiled_rules)
