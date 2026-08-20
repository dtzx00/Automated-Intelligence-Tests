"""CWT – Creative Writing Task instruct."""
import random

WRITING_CUES_3_WORD = [
    ["stamp", "letter", "send"],
    ["belief", "faith", "sing"],
    ["petrol", "diesel", "pump"],
    ["organ", "empire", "comply"],
    ["statement", "stealth", "detect"],
    ["gloom", "payment", "exist"],
    ["year", "week", "embark"],
]

WRITING_CUES_2_WORD = [
    ["stamp", "letter"],
    ["letter", "send"],
    ["belief", "faith"],
    ["faith", "sing"],
    ["petrol", "diesel"],
    ["diesel", "pump"],
    ["organ", "empire"],
    ["empire", "comply"],
    ["statement", "stealth"],
    ["stealth", "detect"],
    ["gloom", "payment"],
    ["payment", "exist"],
    ["year", "week"],
    ["week", "embark"],
    ["death", "sky"],
    ["enemy", "shade"],
    ["joy", "lie"],
    ["marriage", "illness"],
    ["delay", "simplicity"],
    ["frame", "glow"],
    ["sky", "glow"],
    ["death", "frame"],
    ["enemy", "death"],
    ["superpower", "glow"],
]

WRITING_CUES_1_WORD = [
    ["frame"],
    ["glow"],
    ["death"],
    ["sky"],
    ["enemy"],
    ["shade"],
    ["joy"],
    ["lie"],
    ["marriage"],
    ["illness"],
    ["delay"],
    ["simplicity"],
    ["superpower"],
    ["2305"],
    ["Execution"],
]

CUES_BY_N = {
    1: WRITING_CUES_1_WORD,
    2: WRITING_CUES_2_WORD,
    3: WRITING_CUES_3_WORD,
}

TEMPLATE = (
    "Write a short creative story of about five to six sentences "
    "that includes all of these word(s): {cue}.\n\n"
    "Rules:\n"
    "1. Use your imagination and be creative.\n"
    "2. Include every cue word at least once.\n"
    "3. Aim for five to six sentences.\n\n"
    "Notes:\n"
    "Return only the story text itself. Do not include a title, headings, or any commentary."
)


def instruct(cue=None, n_words=3, seed=None):
    """Return instructions for the Creative Writing Task (CWT).

    Parameters
    ----------
    cue : list of str, optional
        Explicit cue words to use. If None, sample from the standard set.
    n_words : int, default 3
        Number of cue words to sample when `cue` is None. Must be 1, 2 or 3.
        Ignored when `cue` is provided.
    seed : int, optional
        Random seed for reproducible sampling of cues.
    """
    if n_words not in CUES_BY_N:
        raise ValueError("n_words must be 1, 2 or 3")
    rng = random.Random(seed)
    if cue is None:
        cue = list(rng.choice(CUES_BY_N[n_words]))
    else:
        cue = list(cue)
    return {
        "test": "cwt",
        "cue": cue,
        "n_words": len(cue),
        "instructions": TEMPLATE.format(cue=", ".join(cue)),
        "response_format": {"cue": cue, "story": "..."},
    }
