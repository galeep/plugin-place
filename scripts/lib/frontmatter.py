"""Read and minimally edit YAML frontmatter without reserializing it.

String-level on purpose: a YAML round-trip would reorder keys and reflow
multiline `description:` blocks. We only ever READ scalar fields and INSERT
one line, so substring handling is sufficient and lossless.
"""
import re

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def split_frontmatter(text):
    """Return (frontmatter_str, body_str). frontmatter_str is None if absent."""
    m = _FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def get_field(frontmatter, key):
    """First top-level (zero-indent) scalar value for `key`, or None."""
    if frontmatter is None:
        return None
    for line in frontmatter.splitlines():
        m = re.match(rf"^{re.escape(key)}:[ \t]*(.+?)[ \t]*$", line)
        if m:
            return _unquote(m.group(1))
    return None


def get_nested_field(frontmatter, parent, key):
    """Value of `key` nested under a top-level `parent:` block, or None."""
    if frontmatter is None:
        return None
    in_parent = False
    for line in frontmatter.splitlines():
        if re.match(rf"^{re.escape(parent)}:[ \t]*$", line):
            in_parent = True
            continue
        if in_parent:
            if re.match(r"^\S", line):  # dedent: left the block
                in_parent = False
                continue
            m = re.match(rf"^[ \t]+{re.escape(key)}:[ \t]*(.+?)[ \t]*$", line)
            if m:
                return _unquote(m.group(1))
    return None
