import random
from pathlib import Path

PAIRS_FILE = Path(__file__).parent / "data" / "cat_word_pairs_en.txt"

INSTRUCTIONS = (
    "For each word pair, enter a single word that is as similar as possible, "
    "in all meanings and uses, to both words in the pair.\n\n"
    "Rules:\n"
    "Your word must be similar to both words in the word pair.\n"
    "Your word must be a single word in English (no open or hyphenated compounds).\n"
    "Your word must not be a proper noun (no specific people, places or brands).\n"
    "Your word must not be a specialized vocabulary or technical term (no abbreviations).\n\n"
    "Notes:\n"
    "Return only that single word for each pair. Do not return anything else."
)


def _load_pairs():
    pairs = []
    with open(PAIRS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and "," in line:
                a, b = line.split(",", 1)
                pairs.append((a.strip(), b.strip()))
    return pairs


def instruct(single_item=False, n_words=10, seed=None):
    """Generate CAT stimuli.

    single_item=True: sample one pair, put it into the instructions text,
    and return a simple response_format {"word_1": ..., "word_2": ..., "word_user": "..."}.
    single_item=False (default): sample n_words unique-word pairs and return
    the multi-item format with "items" list + response_format of wordset_N.
    """
    rng = random.Random(seed)
    pairs = list(_load_pairs())
    used = set()
    items = []
    target = 1 if single_item else n_words
    while len(items) < target and pairs:
        i = rng.randrange(len(pairs))
        a, b = pairs.pop(i)
        if a in used or b in used:
            continue
        used.add(a)
        used.add(b)
        if rng.choice([True, False]):
            a, b = b, a
        items.append({"id": len(items) + 1, "word_1": a, "word_2": b})

    if single_item and items:
        pair = items[0]
        instructions = (
            f"Enter a single word that is as similar as possible, in all meanings and uses, "
            f"to both words in the pair: \"{pair['word_1']}\" and \"{pair['word_2']}\".\n\n"
            "Rules:\n"
            "Your word must be similar to both words in the word pair.\n"
            "Your word must be a single word in English (no open or hyphenated compounds).\n"
            "Your word must not be a proper noun (no specific people, places or brands).\n"
            "Your word must not be a specialized vocabulary or technical term (no abbreviations).\n\n"
            "Notes:\n"
            "Return only that single word. Do not return anything else."
        )
        return {
            "test": "cat",
            "instructions": instructions,
            "items": items,
            "response_format": {
                "word_1": pair["word_1"],
                "word_2": pair["word_2"],
                "word_user": "...",
            },
        }

    return {
        "test": "cat",
        "instructions": INSTRUCTIONS,
        "items": items,
        "response_format": {
            f"wordset_{i['id']}": {
                "word_1": i["word_1"],
                "word_2": i["word_2"],
                "word_user": "...",
            }
            for i in items
        },
    }
