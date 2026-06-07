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
    """First top-level (zero-indent) scalar value for `key`, or None.

    Intended for single-line scalars (name, license, author). For a block
    scalar (`key: >` / `key: |`) it returns the indicator, not the folded
    text — callers in this repo only read single-line fields, so that path is
    intentionally unsupported rather than parsed.
    """
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


def yaml_dq(value):
    """Double-quote a scalar for YAML, escaping backslashes, quotes, newlines."""
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )
    return f'"{escaped}"'


VENDOR_MARK = "via galeep"


def inject_author(text, author):
    """Ensure a top-level `author:` carrying the '<VENDOR_MARK>' vendor mark.

    - No top-level `author:` line: insert `author: "<author>"` after `name:`.
      (`author` is the precomputed vendor string and already ends in the mark.)
    - Existing author without the mark (e.g. upstream `author: "K-Dense, Inc."`):
      append ' <VENDOR_MARK>' to its value, preserving the upstream text.
    - Existing author already carrying the mark: unchanged (idempotent rebuilds).

    Raises ValueError if there is no frontmatter to edit.
    """
    head, body = split_frontmatter(text)
    if head is None:
        raise ValueError("inject_author: no frontmatter present")

    existing = get_field(head, "author")
    if existing is not None:
        if VENDOR_MARK in existing:
            return text
        marked = f"author: {yaml_dq(existing + ' ' + VENDOR_MARK)}"
        out = [
            marked if re.match(r"^author:[ \t]*\S", line) else line
            for line in head.splitlines()
        ]
        return "---\n" + "\n".join(out) + "\n---\n" + body

    author_line = f"author: {yaml_dq(author)}"
    out, inserted = [], False
    for line in head.splitlines():
        out.append(line)
        if not inserted and re.match(r"^name:[ \t]*", line):
            out.append(author_line)
            inserted = True
    if not inserted:
        out.insert(0, author_line)
    return "---\n" + "\n".join(out) + "\n---\n" + body
