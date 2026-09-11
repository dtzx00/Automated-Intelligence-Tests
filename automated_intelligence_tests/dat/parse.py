"""DAT parse: raw model or human text → ait.evaluate('dat', ...) input.

Olson, J. A., Nahas, J., Chmoulevitch, D., Cropper, S. J., & Webb, M. E.
(2021). Naming unrelated words predicts creativity. PNAS, 118(25),
e2022340118.

This module only extracts a word list from free text. Official validity
rules (strip non-letters except hyphen/space, compound candidates,
dictionary / vocab check), uniqueness-at-score-time, the first-7 cutoff,
and GloVe-840B cosine distance × 100 live in evaluate.py. Do not fold
those into parse.
"""
from __future__ import annotations

import re

FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*?)\n?```", flags=re.S)
UNCLOSED_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*)$", flags=re.S)
THINK_RE = re.compile(
    r"<(?:think|thinking|reasoning)>.*?</(?:think|thinking|reasoning)>",
    flags=re.S | re.I,
)
ITEM_LABEL_RE = re.compile(
    r"""^\s*(?:
        \d+\s*[\.\)\:] |
        [-*•] |
        (?:word|noun|item)[_\s-]?\d+\s*[:=]
    )\s*""",
    flags=re.I | re.X,
)
PREAMBLE_HINT = re.compile(
    r"""^(?:
        (?:sure|certainly|of\ course|okay|ok|alright|right|yes|yeah|got\ it)[!.,]?\s*
      | (?:here|this|these|the|my|your)
      | (?:nouns?|words?|items?|list|answer|response|output)
      | (?:i(?:'|’)ll|i\ will|let\ me)
    )""",
    flags=re.I | re.X,
)
LABEL_ONLY_LINE = re.compile(
    r"""^\s*(?:
        (?:sure|certainly|of\ course|okay|ok|alright|right|yes|yeah|got\ it)[!.,]*
      | (?:here(?:'|’)s|here\ is|here\ are|here\ they\ are|here\ you\ (?:go|are))
          (?:\s+\w+){0,8}
      | (?:the\ )?(?:(?:ten|10|following|requested|distinct)\s+)?
          (?:nouns?|words?|items?|list)
          (?:\s+(?:are|is|follow(?:s|ing)?))?
    )\s*:?\s*$""",
    flags=re.I | re.X,
)
JSON_WORD_RE = re.compile(
    r"""["']?(?:word|noun|item)[_\s-]?(\d+)["']?\s*[:=]\s*["']([^"']+)["']""",
    flags=re.I,
)


def _unwrap_fences(text, first=False):
    if "```" not in text:
        return text
    chunks = [m.group(1).strip() for m in FENCE_RE.finditer(text) if m.group(1).strip()]
    if chunks:
        return chunks[0] if first else "\n".join(chunks)
    m = UNCLOSED_FENCE_RE.search(text)
    return m.group(1).strip() if m else text


def _strip_preamble(text):
    text = text.strip().strip("\"'`")
    while True:
        lines = text.splitlines()
        if not lines or not LABEL_ONLY_LINE.match(lines[0]):
            break
        text = "\n".join(lines[1:]).strip()
    if ":" in text:
        left, right = text.split(":", 1)
        left_s = left.strip()
        if (
            right.strip()
            and len(left_s) <= 80
            and not ITEM_LABEL_RE.match(left_s + ":")
            and PREAMBLE_HINT.match(left_s)
        ):
            text = right.strip()
    return text.strip()


def parse(raw, cue=None, n_words=10, stim=None, **kwargs):
    """Raw DAT text → list[str] for evaluate(), or None.

    Parameters
    ----------
    raw : str
        Model or participant text.
    cue : unused
        Accepted for API consistency with the other tests. DAT scoring
        does not use a cue (Olson et al., 2021).
    n_words : int, default 10
        Cap on extracted nouns. Matches instruct(n_words=10).
    stim : dict, optional
        Full instruct() return value. n_words is read from stim when
        given and n_words was left at the default.

    Returns
    -------
    list[str] or None
        Candidate nouns in order, de-duplicated case-insensitively.
        None if nothing usable was found. evaluate() still applies
        Olson validity and returns score=None when fewer than 7
        unique valid words remain.
    """
    if stim:
        if n_words == 10 and stim.get("n_words"):
            try:
                n_words = int(stim["n_words"])
            except (TypeError, ValueError):
                pass
    try:
        n_words = int(n_words)
    except (TypeError, ValueError):
        n_words = 10
    if n_words < 1:
        n_words = 10

    text = str(raw or "").strip()
    if not text:
        return None
    text = _unwrap_fences(THINK_RE.sub(" ", text))
    pairs = JSON_WORD_RE.findall(text)
    if len(pairs) >= 3:
        tokens = [p[1].strip() for p in sorted(pairs, key=lambda p: int(p[0]))]
    else:
        tokens = [
            ITEM_LABEL_RE.sub("", p).strip().strip("\"'`")
            for p in re.split(r"[,;\n\r]+", _strip_preamble(text))
        ]
        tokens = [t for t in tokens if t]
        if len(tokens) == 1 and " " in tokens[0]:
            words = tokens[0].split()
            if 7 <= len(words) <= 12:
                tokens = words
    nouns, seen = [], set()
    for t in tokens:
        t = t.strip()
        # Drop sentence-like fragments. Keep short compounds ("cul de sac").
        if t.count(" ") >= 3 or (t.endswith(".") and " " in t):
            continue
        key = t.lower()
        if not t or key in seen:
            continue
        seen.add(key)
        nouns.append(t)
        if len(nouns) == n_words:
            break
    return nouns or None
