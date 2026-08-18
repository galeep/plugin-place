"""Normalize the heterogeneous `license:` strings in upstream skills and resolve
a single plugin-level license (or a 'mixed' sentinel)."""

MIXED = "mixed (see individual skills)"

_NORMALIZE = {
    "mit": "MIT",
    "mit license": "MIT",
    "bsd license": "BSD",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-2-clause license": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd-3-clause license": "BSD-3-Clause",
    "3-clause bsd license": "BSD-3-Clause",
    "3 clause bsd license": "BSD-3-Clause",
    "apache-2.0": "Apache-2.0",
    "apache-2.0 license": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "gpl-2.0 license": "GPL-2.0",
    "gpl-3.0 license": "GPL-3.0",
    "gplv3 license": "GPL-3.0",
    "cc-by-4.0": "CC-BY-4.0",
    "https://creativecommons.org/licenses/by/4.0/": "CC-BY-4.0",
    "proprietary. license.txt has complete terms": "Proprietary",
    "proprietary (api key required)": "Proprietary",
    "unknown": "Unknown",
    "": "Unknown",
}


def normalize(raw):
    """Canonical token for a raw license string. Unknown values pass through
    verbatim (so a missed variant degrades to 'mixed', never a false uniform)."""
    if raw is None:
        return "Unknown"
    key = raw.strip().lower()
    if key in _NORMALIZE:
        return _NORMALIZE[key]
    return raw.strip() or "Unknown"


def resolve_plugin_license(normalized_licenses):
    """Single value if all member licenses agree, else the MIXED sentinel.
    Empty input -> 'Unknown'."""
    uniq = sorted(set(normalized_licenses))
    if not uniq:
        return "Unknown"
    if len(uniq) == 1:
        return uniq[0]
    return MIXED


# ── License-drift tripwire ────────────────────────────────────────────────
#
# The `license:` value in plugins.yaml is a static human declaration: nothing
# in the build ever checked it against what the upstream actually ships. That
# is fine until an upstream relicenses. caveman v2.1.0 did exactly that (MIT ->
# split MIT + BSL-1.1), and it moved through the build silently — the nightly
# sync workflow's review summary counts `plugins/<name>/LICENSE` as one
# anonymous increment to its "asset/other" file tally, so a relicense is
# indistinguishable from a typo fix in a README.
#
# These helpers give the license layer the same fail-loud guarantee the patch
# anchors already have: record a fingerprint of the upstream's licensing
# documents at the reviewed pin, and abort the build when it moves.
#
# SCOPE, stated plainly: this detects changes to the licensing DOCUMENTS at an
# upstream's root. It does not read per-directory license tables, and it cannot
# see a new subdirectory that inherits a restrictive default without any
# document changing. It catches the case that actually occurred and turns it
# from silent into loud; it is not a compliance audit.

import hashlib  # noqa: E402
import re  # noqa: E402

# Matched case-insensitively against filenames at the upstream checkout root.
# Broader than "LICENSE" because upstreams ship LICENSE.md, LICENCE,
# LICENSE.BSL, COPYING, NOTICE — and LICENSING.md, the file that carried
# caveman's per-directory split, which a plain `licen[sc]e` pattern misses.
#
# The stem is an explicit alternation rather than `licen[sc]\w*`: the loose
# form also swallows ordinary source files like `licensed_under.py`, whose
# churn would raise spurious drift reports and train the reader to ignore
# them. A separator is required before any suffix, so `licenses.py` does not
# match while `LICENSE.md`, `LICENSE.BSL` and `LICENSE-MIT` all do.
_LICENSE_DOC_RE = re.compile(
    r"^(licen[sc]e|licen[sc]ing|copying|notice)([-.][\w.-]+)?$", re.IGNORECASE
)


def license_docs(root):
    """Licensing documents at an upstream checkout root, sorted by name.

    Returns None when the checkout is not present — NOT an empty list. The
    distinction is load-bearing and was got wrong twice here, the second time
    while fixing the first.

    An uninitialised submodule leaves `vendor/<name>/` EMPTY BUT EXISTING, which
    is the DEFAULT state of a fresh clone (`git clone` without
    --recurse-submodules): git materialises the directory for the gitlink and
    puts nothing in it. So `root.is_dir()` is True and a missing-directory check
    alone sails straight past the case it was written for.

    Folding that into "[] — no license documents" makes the fingerprint the
    sha256 of nothing, identically for every upstream. Recording that value then
    reports "License documents unchanged at every pinned upstream" forever,
    disarming the tripwire permanently — and the documented remedy for a drift
    report is to re-run `--write`, so the instruction and the disarm would be
    the same command.

    An EMPTY directory is therefore unverifiable. A populated checkout that
    genuinely ships no licensing document is a real state and still returns [];
    that is a fact about the upstream, not a broken working tree.

    Callers must treat None as "cannot verify" and refuse to record it, never as
    "verified clean".
    """
    if not root.is_dir():
        return None
    if not any(root.iterdir()):
        return None
    return sorted(
        (p for p in root.iterdir() if p.is_file() and _LICENSE_DOC_RE.match(p.name)),
        key=lambda p: p.name,
    )


def fingerprint_docs(root):
    """Stable sha256 over every licensing document at `root`, or None.

    None propagates from license_docs when the root is unreadable (see there:
    an uninitialised submodule must not hash to a recordable value).

    Hashes each document's NAME as well as its bytes, so adding or removing a
    document moves the fingerprint even when every pre-existing file is
    untouched. caveman v2.1.0 is the motivating case: it edited LICENSE and
    added LICENSE.BSL + LICENSING.md, and a contents-only hash of the files we
    already knew about would have understated the change.

    NUL separators keep the stream unambiguous: without them a rename that
    shifts a byte between the name and content fields could collide.
    """
    docs = license_docs(root)
    if docs is None:
        return None
    h = hashlib.sha256()
    for p in docs:
        h.update(p.name.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


# A recorded fingerprint must be exactly this shape. YAML will happily hand back
# an int for an unquoted numeric value, and slicing an int raises TypeError —
# which, on the advisory path, would abort the very build that path promises
# never to abort.
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def is_fingerprint(value):
    """True only for a well-formed recorded fingerprint (64 lowercase hex)."""
    return isinstance(value, str) and bool(_FINGERPRINT_RE.match(value))
