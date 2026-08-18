"""DAT instruct: generate instructions."""

INSTRUCTIONS = (
    "Please enter 10 words that are as different from each other as possible, "
    "in all meanings and uses of the words.\n\n"
    "Rules:\n"
    "Only single words in English.\n"
    "Only nouns (things, objects, concepts).\n"
    "No proper nouns (no specific people or places).\n"
    "No specialised vocabulary or technical terms.\n"
    "Think of the words on your own.\n\n"
    "Notes:\n"
    "Return words as comma-separated list. Do not return anything else."
)

def instruct(n_words=10):
    return {
        "test": "dat",
        "instructions": INSTRUCTIONS,
        "n_words": n_words,
        "response_format": {f"word_{i}": "..." for i in range(1, n_words + 1)},
    }
