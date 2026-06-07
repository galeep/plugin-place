"""Vendor attribution strings. The mark is 'via galeep' over the original author."""

AGENT_AUTHOR = "K-Dense, Inc. via galeep"


def skill_author(original):
    """`"<original> via galeep"` when an original author exists, else `"via galeep"`.

    `original` is the upstream `metadata.skill-author`; None/blank means the
    skill carries no author and we add only the vendor mark (no fabrication).
    """
    if original and original.strip():
        return f"{original.strip()} via galeep"
    return "via galeep"
