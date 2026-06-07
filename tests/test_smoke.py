import importlib

def test_lib_package_imports():
    mod = importlib.import_module("scripts.lib")
    assert mod is not None
