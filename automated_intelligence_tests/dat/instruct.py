"""DAT instruct: generate instructions."""


def instruct(cue=None, n_words=10, seed=None):
    """Return instructions for the Divergent Association Task (DAT).

    Parameters
    ----------
    cue : str, optional
        Optional starting word. If provided, the participant is told that the
        first word is given and they should generate the remaining words to be
        as different as possible from each other (and from the cue).
    n_words : int, default 10
        Number of words the participant should produce.
    seed : int, optional
        Reserved for future use (kept for API consistency with other tests).
    """
    if n_words < 1:
        raise ValueError("n_words must be >= 1")

    base_rules = (
        "Rules:\n"
        "Only single words in English.\n"
        "Only nouns (things, objects, concepts).\n"
        "No proper nouns (no specific people or places).\n"
        "No specialised vocabulary or technical terms.\n"
        "Think of the words on your own.\n\n"
        "Notes:\n"
        "Return words as comma-separated list. Do not return anything else."
    )

    if cue is None:
        instructions = (
            f"Please enter {n_words} words that are as different from each other "
            f"as possible, in all meanings and uses of the words.\n\n"
            + base_rules
        )
        response_format = {f"word_{i}": "..." for i in range(1, n_words + 1)}
    else:
        cue = str(cue).strip()
        instructions = (
            f"Please enter {n_words} words that are as different from each other "
            f"as possible, in all meanings and uses of the words.\n\n"
            f"The first word is given to you: {cue}\n\n"
            + base_rules
        )
        # word_1 is the given cue; participant fills the rest
        response_format = {"word_1": cue}
        response_format.update(
            {f"word_{i}": "..." for i in range(2, n_words + 1)}
        )

    return {
        "test": "dat",
        "cue": cue,
        "n_words": n_words,
        "instructions": instructions,
        "response_format": response_format,
    }
