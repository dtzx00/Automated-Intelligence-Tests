"""DAT instruct: generate instructions."""

CUE = [
    "brick", "paperclip", "bucket", "sock", "fork", "knife",
    "pencil", "pillow", "broom", "belt", "hat", "purse",
    "comb", "baseball", "candle", "clock", "lighter", "lamp"]

INSTRUCTIONS_less_cue = (
    f"Please enter {n_words} words that are as different from each other as possible, "
    "in all meanings and uses of the words.\n\n"
    "Rules:\n"
    "Only single words in English.\n"
    "Only nouns (things, objects, concepts).\n"
    "No proper nouns (no specific people or places).\n"
    "No specialised vocabulary or technical terms.\n"
    "Think of the words on your own.\n\n"
    "Notes:\n"
    "Return words as comma-separated list. Do not return anything else.")

INSTRUCTIONS_with_cue = (
    f"Please enter {n_words} words that are as different from each other as possible, "
    "in all meanings and uses of the words.\n\n"
    "Rules:\n"
    "Only single words in English.\n"
    "Only nouns (things, objects, concepts).\n"
    "No proper nouns (no specific people or places).\n"
    "No specialised vocabulary or technical terms.\n"
    "Think of the words on your own.\n\n"
    "Notes:\n"
    "Return words as comma-separated list. Do not return anything else.\n"
    f"The first word is given to you, {cue}")

def instruct(n_words=10):
    return {
        "test": "dat",
        "cue":cue,
        "instructions": INSTRUCTIONS_with_cue if cue is not None else INSTRUCTIONS_less_cue,
        "n_words": n_words,
        "response_format": {f"word_{i}": "..." for i in range(1, n_words + 1)},
    }
