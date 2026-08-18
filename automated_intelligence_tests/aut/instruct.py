"""AUT – Alternative Uses Task instruct."""
import random

AUT_OBJECTS = [
    "brick", "paperclip", "bucket", "sock", "fork", "knife",
    "pencil", "pillow", "broom", "belt", "hat", "purse",
    "comb", "baseball", "candle", "clock", "lighter", "lamp",
]

TEMPLATE = (
    "What are some creative uses for this object: {object}?\n\n"
    "The goal is to come up with creative uses, which are ideas that may strike "
    "as clever, unusual, interesting, uncommon, humorous, innovative, or different.\n\n"
    "Rules:\n"
    "1. List as many creative uses as you can.\n"
    "2. Answer in short phrases, one use per line.\n"
    "3. Return only the list of uses, nothing else.\n"
    "4. Do not return any thought process or explanations other than the list of uses.\n\n"
    "Notes:\n"
    "Return the uses as a plain list (one per line). Do not return anything else."
)

def instruct(object=None, seed=None):
    rng = random.Random(seed)
    obj = object if object is not None else rng.choice(AUT_OBJECTS)
    return {
        "test": "aut",
        "object": obj,
        "instructions": TEMPLATE.format(object=obj),
        "response_format": {"object": obj, "uses": ["use 1", "use 2", "..."]},
    }
