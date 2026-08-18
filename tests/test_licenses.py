from scripts.lib import licenses as lic

def test_normalize_mit_variants():
    assert lic.normalize("MIT") == "MIT"
    assert lic.normalize("MIT license") == "MIT"
    assert lic.normalize("MIT License") == "MIT"

def test_normalize_apache_and_bsd():
    assert lic.normalize("Apache-2.0 license") == "Apache-2.0"
    assert lic.normalize("Apache-2.0") == "Apache-2.0"
    assert lic.normalize("BSD-3-Clause license") == "BSD-3-Clause"
    assert lic.normalize("BSD-3-Clause") == "BSD-3-Clause"

def test_normalize_same_license_spelling_variants():
    # real upstream values that must NOT split a plugin into 'mixed'
    assert lic.normalize("3-clause BSD license") == "BSD-3-Clause"
    assert lic.normalize("3 clause BSD license") == "BSD-3-Clause"
    assert lic.normalize("Apache License, Version 2.0") == "Apache-2.0"
    # normalized-then-resolved (as render.py uses it): mixed BSD-3 spellings
    # collapse so the plugin stays uniform rather than falsely 'mixed'
    raw = ["BSD-3-Clause license", "3 clause BSD license", "BSD-3-Clause"]
    assert lic.resolve_plugin_license([lic.normalize(x) for x in raw]) == "BSD-3-Clause"

def test_normalize_cc_by():
    assert lic.normalize("CC-BY-4.0") == "CC-BY-4.0"
    assert lic.normalize("https://creativecommons.org/licenses/by/4.0/") == "CC-BY-4.0"

def test_normalize_unknown_and_none():
    assert lic.normalize(None) == "Unknown"
    assert lic.normalize("") == "Unknown"
    assert lic.normalize("Unknown") == "Unknown"

def test_normalize_proprietary_variants():
    assert lic.normalize("Proprietary. LICENSE.txt has complete terms") == "Proprietary"
    assert lic.normalize("Proprietary (API key required)") == "Proprietary"

def test_normalize_passthrough():
    weird = "CeCILL FREE SOFTWARE LICENSE AGREEMENT"
    assert lic.normalize(weird) == weird

def test_resolve_uniform():
    assert lic.resolve_plugin_license(["MIT", "MIT", "MIT"]) == "MIT"

def test_resolve_mixed():
    assert lic.resolve_plugin_license(["MIT", "GPL-3.0"]) == "mixed (see individual skills)"

def test_resolve_empty():
    assert lic.resolve_plugin_license([]) == "Unknown"


# ── License-drift tripwire ────────────────────────────────────────────────

def _write(root, name, text):
    p = root / name
    p.write_text(text)
    return p


def test_license_docs_matches_the_real_upstream_filenames(tmp_path):
    # Every spelling seen across the four pinned upstreams, plus the two that a
    # naive `licen[sc]e` pattern misses: LICENSING.md (which carried caveman's
    # per-directory split) and LICENSE.BSL.
    for name in ("LICENSE", "LICENSE.md", "LICENCE", "LICENSE.BSL",
                 "LICENSING.md", "COPYING", "NOTICE"):
        _write(tmp_path, name, "x")
    found = [p.name for p in lic.license_docs(tmp_path)]
    assert "LICENSING.md" in found
    assert "LICENSE.BSL" in found
    assert len(found) == 7


def test_license_docs_ignores_unrelated_files_and_dirs(tmp_path):
    # Source files whose names merely start with "licen" must not be treated as
    # licensing documents: their churn would raise drift reports that are always
    # noise, which is how a notification gate gets trained into background hum.
    _write(tmp_path, "LICENSE", "x")
    _write(tmp_path, "README.md", "x")
    _write(tmp_path, "licensed_under.py", "x")  # suffix without a separator
    _write(tmp_path, "licenses.py", "x")        # plural stem, ordinary module
    (tmp_path / "licenses").mkdir()             # a directory, not a file
    assert [p.name for p in lic.license_docs(tmp_path)] == ["LICENSE"]


def test_license_docs_keeps_hyphen_and_dot_suffixed_documents(tmp_path):
    # The separator rule must not cost real documents.
    for name in ("LICENSE-MIT", "LICENSE.BSL", "COPYING.LESSER"):
        _write(tmp_path, name, "x")
    assert len(lic.license_docs(tmp_path)) == 3


def test_license_docs_missing_root_is_none_not_empty(tmp_path):
    # None means "cannot verify" and must never be recorded as a fingerprint.
    assert lic.license_docs(tmp_path / "nope") is None
    assert lic.fingerprint_docs(tmp_path / "nope") is None


def test_license_docs_empty_dir_is_none(tmp_path):
    # THE fresh-clone case, and the one a missing-directory check sails past:
    # `git clone` without --recurse-submodules materialises vendor/<name>/ as an
    # existing but EMPTY directory, so is_dir() is True. Treating that as "no
    # license documents" hashes it to sha256 of nothing — identically for every
    # upstream — which reads as "verified clean" forever after.
    empty = tmp_path / "vendor-sub"
    empty.mkdir()
    assert lic.license_docs(empty) is None
    assert lic.fingerprint_docs(empty) is None


def test_populated_checkout_without_license_docs_is_empty_not_none(tmp_path):
    # A real checkout that genuinely ships no licensing document is a fact about
    # the upstream, not a broken working tree, and must stay verifiable.
    root = tmp_path / "sub"
    root.mkdir()
    _write(root, "README.md", "x")
    assert lic.license_docs(root) == []
    assert lic.fingerprint_docs(root) is not None


def test_is_fingerprint_rejects_non_str_and_malformed():
    # plugins.yaml is hand-editable and YAML types an unquoted 1234... as an int.
    # Slicing an int raised TypeError on the advisory path, aborting the build
    # that path promises never to abort.
    assert lic.is_fingerprint("z" * 64) is False      # not hex
    assert lic.is_fingerprint("a" * 64) is True       # 'a' IS a hex digit
    assert lic.is_fingerprint("0" * 64) is True
    assert lic.is_fingerprint(12345) is False
    assert lic.is_fingerprint(None) is False
    assert lic.is_fingerprint("00feaa42") is False    # too short
    assert lic.is_fingerprint("F" * 64) is False      # uppercase


def test_fingerprint_is_stable_and_order_independent(tmp_path):
    _write(tmp_path, "LICENSE", "MIT text")
    _write(tmp_path, "NOTICE", "notice text")
    assert lic.fingerprint_docs(tmp_path) == lic.fingerprint_docs(tmp_path)


def test_fingerprint_moves_when_contents_change(tmp_path):
    _write(tmp_path, "LICENSE", "MIT text")
    before = lic.fingerprint_docs(tmp_path)
    _write(tmp_path, "LICENSE", "MIT text, amended")
    assert lic.fingerprint_docs(tmp_path) != before


def test_fingerprint_moves_when_a_document_is_added(tmp_path):
    # The caveman v2.1.0 case: LICENSE was edited AND LICENSE.BSL/LICENSING.md
    # appeared. A contents-only hash of known files would understate that, so
    # adding a document alone must move the fingerprint.
    _write(tmp_path, "LICENSE", "MIT text")
    before = lic.fingerprint_docs(tmp_path)
    _write(tmp_path, "LICENSE.BSL", "BSL text")
    assert lic.fingerprint_docs(tmp_path) != before


def test_fingerprint_moves_when_a_document_is_removed(tmp_path):
    _write(tmp_path, "LICENSE", "MIT text")
    _write(tmp_path, "LICENSE.BSL", "BSL text")
    before = lic.fingerprint_docs(tmp_path)
    (tmp_path / "LICENSE.BSL").unlink()
    assert lic.fingerprint_docs(tmp_path) != before


def test_fingerprint_distinguishes_name_from_content_boundary(tmp_path):
    # Without a separator between name and bytes, ("AB", "C") and ("A", "BC")
    # would hash identically. Guard the framing.
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _write(a, "LICENSE", "AB")
    _write(b, "LICENSE", "A")          # same doc name, different split
    _write(b, "LICENSE.md", "B")
    assert lic.fingerprint_docs(a) != lic.fingerprint_docs(b)


def test_empty_root_fingerprint_differs_from_populated(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    _write(tmp_path, "LICENSE", "MIT text")
    assert lic.fingerprint_docs(empty) != lic.fingerprint_docs(tmp_path)
