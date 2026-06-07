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

def test_normalize_passthrough():
    weird = "CeCILL FREE SOFTWARE LICENSE AGREEMENT"
    assert lic.normalize(weird) == weird

def test_resolve_uniform():
    assert lic.resolve_plugin_license(["MIT", "MIT", "MIT"]) == "MIT"

def test_resolve_mixed():
    assert lic.resolve_plugin_license(["MIT", "GPL-3.0"]) == "mixed (see individual skills)"

def test_resolve_empty():
    assert lic.resolve_plugin_license([]) == "Unknown"
