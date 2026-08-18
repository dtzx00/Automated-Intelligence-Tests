"""Automated Intelligence Tests: CAT, DAT, AUT and WRT.

Minimal package for association, alternative-uses and creative-writing tests.
"""

import os
import json
from pathlib import Path

from cat.instruct import instruct as cat_instruct
from cat.evaluate import evaluate as cat_evaluate
from dat.instruct import instruct as dat_instruct
from dat.evaluate import evaluate as dat_evaluate
from aut.instruct import instruct as aut_instruct
from aut.evaluate import evaluate as aut_evaluate
from wrt.instruct import instruct as wrt_instruct
from wrt.evaluate import evaluate as wrt_evaluate

__version__ = "0.1.1"


def list_available_tests(verbose: bool = True) -> list:
    """Scan test directories with os.listdir() and load their metadata.json."""
    root = Path(__file__).resolve().parent
    tests = []
    for name in sorted(os.listdir(root)):
        meta_path = root / name / "metadata.json"
        if (root / name).is_dir() and meta_path.is_file():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                meta["directory"] = name
                tests.append(meta)
            except Exception:
                continue
    if verbose:
        for t in tests:
            print(f"{t.get('short_name', '?')}: {t.get('long_name', '')}")
            print(f"  {t.get('description', '')}\n")
    return tests


def instruct(test: str, **kwargs):
    if test == "cat":
        return cat_instruct(**kwargs)
    if test == "dat":
        return dat_instruct(**kwargs)
    if test == "aut":
        return aut_instruct(**kwargs)
    if test == "wrt":
        return wrt_instruct(**kwargs)
    raise ValueError(
        f"Unknown test: {test}. Use 'cat', 'dat', 'aut' or 'wrt'. "
        "Call list_available_tests() to see details."
    )


def evaluate(test: str, responses, **kwargs):
    if test == "cat":
        return cat_evaluate(responses, **kwargs)
    if test == "dat":
        return dat_evaluate(responses, **kwargs)
    if test == "aut":
        return aut_evaluate(responses, **kwargs)
    if test == "wrt":
        return wrt_evaluate(responses, **kwargs)
    raise ValueError(
        f"Unknown test: {test}. Use 'cat', 'dat', 'aut' or 'wrt'. "
        "Call list_available_tests() to see details."
    )
