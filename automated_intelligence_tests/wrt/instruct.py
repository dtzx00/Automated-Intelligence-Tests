"""WRT – Creative Writing Task instruct."""
import random

WRITING_CUES = [
    ["stamp", "letter", "send"],
    ["belief", "faith", "sing"],
    ["petrol", "diesel", "pump"],
    ["organ", "empire", "comply"],
    ["statement", "stealth", "detect"],
    ["gloom", "payment", "exist"],
    ["year", "week", "embark"],
]

TEMPLATE = (
    "Write a short creative story of about five to six sentences "
    "that includes all three of these words: {cues}.\n\n"
    "Rules:\n"
    "1. Use your imagination and be creative.\n"
    "2. Include every cue word at least once.\n"
    "3. Aim for five to six sentences.\n\n"
    "Notes:\n"
    "Return only the story text itself. Do not include a title, headings, or any commentary."
)

def instruct(cues=None, seed=None):
    rng = random.Random(seed)
    if cues is None:
        cues = list(rng.choice(WRITING_CUES))
    else:
        cues = list(cues)
    return {
        "test": "wrt",
        "cues": cues,
        "instructions": TEMPLATE.format(cues=", ".join(cues)),
        "response_format": {"cues": cues, "story": "..."},
    }
