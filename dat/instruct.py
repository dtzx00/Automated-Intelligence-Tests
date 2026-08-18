"""DAT instruct: generate instructions."""

INSTRUCTIONS = (
    "Please enter 10 words that are as different from each other as possible, "
    "in all meanings and uses of the words.\n\n"
    "Rules:\n"
    "1. Only single words in English.\n"
    "2. Only nouns (things, objects, concepts).\n"
    "3. No proper nouns (no specific people or places).\n"
    "4. No specialised vocabulary or technical terms.\n"
    "5. Think of the words on your own.\n\n"
    "Return the 10 words."
)

def instruct(n_words=10):
    return {
        "test": "dat",
        "instructions": INSTRUCTIONS,
        "n_words": n_words,
        "response_format": {f"word_{i}": "..." for i in range(1, n_words + 1)},
    }
