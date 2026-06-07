"""Convert a K-Dense AGENTS.md profile into a Claude Code subagent file.

Frontmatter is synthesized from catalog metadata; the profile body is kept
verbatim (faithful provenance, drift detection stays meaningful).
"""
from .frontmatter import yaml_dq


def synth_subagent(profile_text, slug, profession, summary, author):
    """Return subagent `.md` content: synthesized frontmatter + verbatim body."""
    description = f"{profession}: {summary}"
    head = "\n".join([
        "---",
        f"name: {slug}",
        f"description: {yaml_dq(description)}",
        f"author: {yaml_dq(author)}",
        "---",
        "",
    ])
    return head + profile_text
