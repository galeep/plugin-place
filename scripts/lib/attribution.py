"""Vendor attribution strings. The mark is 'via galeep' over the original author."""

AGENT_AUTHOR = "K-Dense, Inc. via galeep"


def skill_author(original, fallback=None):
    """`"<author> via galeep"` where author is the per-file skill-author if
    present, else the upstream's known author `fallback` if given, else just the
    vendor mark `"via galeep"` (no fabrication when the origin is unknown).

    `original` is the upstream `metadata.skill-author`. `fallback` is the
    upstream's declared author (e.g. caveman -> "Julius Brussee"); upstreams
    with mixed/third-party origins leave it unset so unknown files stay bare.
    """
    name = (original or "").strip() or (fallback or "").strip()
    return f"{name} via galeep" if name else "via galeep"
