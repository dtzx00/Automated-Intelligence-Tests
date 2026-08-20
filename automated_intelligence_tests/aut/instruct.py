"""AUT – Alternative Uses Task instruct."""
import random

CUE = [
    "brick", "paperclip", "bucket", "sock", "fork", "knife",
    "pencil", "pillow", "broom", "belt", "hat", "purse",
    "comb", "baseball", "candle", "clock", "lighter", "lamp"]

TEMPLATE = (
    "What are some creative uses for this object: {cue}?\n\n"
    "The goal is to come up with creative uses, which are ideas that may strike "
    "as clever, unusual, interesting, uncommon, humorous, innovative, or different.\n\n"
    "Rules:\n"
    "1. List as many creative uses as you can.\n"
    "2. Answer in short phrases, one use per line.\n"
    "3. Return only the list of uses, nothing else.\n"
    "4. Do not return any thought process or explanations other than the list of uses.\n\n"
    "Notes:\n"
    "Return the uses as a plain list (one per line). Do not return anything else.")


def instruct(cue=None, seed=None):
    """Return instructions for the Alternative Uses Task (AUT).

    Parameters
    ----------
    cue : str, optional
        The object to generate uses for. If None, sample from the standard set.
    seed : int, optional
        Random seed for reproducible sampling of the cue.
    """
    rng = random.Random(seed)
    if cue is None:
        cue = rng.choice(CUE)
    return {
        "test": "aut",
        "cue": cue,
        "instructions": TEMPLATE.format(cue=cue),
        "response_format": {"cue": cue, "responses": ["use 1", "use 2", "..."]},
    }
