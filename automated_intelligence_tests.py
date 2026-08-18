"""Automated Intelligence Tests: CAT, DAT, AUT and WRT.

Minimal package for association, alternative-uses and creative-writing tests.
"""

from cat.instruct import instruct as cat_instruct
from cat.evaluate import evaluate as cat_evaluate
from dat.instruct import instruct as dat_instruct
from dat.evaluate import evaluate as dat_evaluate
from aut.instruct import instruct as aut_instruct
from aut.evaluate import evaluate as aut_evaluate
from wrt.instruct import instruct as wrt_instruct
from wrt.evaluate import evaluate as wrt_evaluate

__version__ = "0.1.0"

def instruct(test: str, **kwargs):
    if test == "cat":
        return cat_instruct(**kwargs)
    if test == "dat":
        return dat_instruct(**kwargs)
    if test == "aut":
        return aut_instruct(**kwargs)
    if test == "wrt":
        return wrt_instruct(**kwargs)
    raise ValueError(f"Unknown test: {test}. Use 'cat', 'dat', 'aut' or 'wrt'.")

def evaluate(test: str, responses, **kwargs):
    if test == "cat":
        return cat_evaluate(responses, **kwargs)
    if test == "dat":
        return dat_evaluate(responses, **kwargs)
    if test == "aut":
        return aut_evaluate(responses, **kwargs)
    if test == "wrt":
        return wrt_evaluate(responses, **kwargs)
    raise ValueError(f"Unknown test: {test}. Use 'cat', 'dat', 'aut' or 'wrt'.")
