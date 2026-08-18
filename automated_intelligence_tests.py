"""Automated Intelligence Tests: CAT and DAT.

Minimal package for convergent and divergent association tests.
"""

from cat.instruct import instruct as cat_instruct
from cat.evaluate import evaluate as cat_evaluate
from dat.instruct import instruct as dat_instruct
from dat.evaluate import evaluate as dat_evaluate

__version__ = "0.1.0"

def instruct(test: str, **kwargs):
    if test == "cat":
        return cat_instruct(**kwargs)
    if test == "dat":
        return dat_instruct(**kwargs)
    raise ValueError(f"Unknown test: {test}. Use 'cat' or 'dat'.")

def evaluate(test: str, responses, **kwargs):
    if test == "cat":
        return cat_evaluate(responses, **kwargs)
    if test == "dat":
        return dat_evaluate(responses, **kwargs)
    raise ValueError(f"Unknown test: {test}. Use 'cat' or 'dat'.")
