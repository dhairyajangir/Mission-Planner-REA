"""Minimal stand-in for the `imp` module removed in Python 3.12, used only to run LogAnalyzer.py (it calls imp.load_source once).
Copied to ~/la/imp.py by run-loganalyzer-py3.sh; it is not part of Mission Planner."""
import importlib.util
import sys


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
