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
