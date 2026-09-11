"""AUT parse: raw model or human text → ait.evaluate('aut', ...) input.

Beaty, R. E., & Johnson, D. R. (2021). Automating creativity assessment
with SemDis: An open platform for computing semantic distance.
Behavior Research Methods, 53, 757–780.

This module only splits free text into use phrases and attaches the cue.
SemDis cleaning (strip marks, drop digits, how='heavy' stopwords, drop
cue + simple plural), multiplicative composition across the five spaces,
and 1 − cosine to the cue live in evaluate.py. Do not fold those into
parse.
"""
from __future__ import annotations

import re

FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*?)\n?```", flags=re.S)
UNCLOSED_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*)$", flags=re.S)
THINK_RE = re.compile(
    r"<(?:think|thinking|reasoning)>.*?</(?:think|thinking|reasoning)>",
    flags=re.S | re.I,
)
AUT_ITEM_LABEL = re.compile(
    r"""^\s*(?:
        [\(\[]?\d+[.)\]:\-–—] |
        [-*•] |
        (?:word|noun|item|use)[_\-\s]?\d+\s*[:=]
    )\s*""",
    flags=re.I | re.X,
)
INLINE_ITEM = re.compile(r"\s+(?:[\(\[]?\d+[.)\]:\-–—]|[-*•])\s+")
AUT_PREAMBLE_LINE = re.compile(
    r"""^\s*(?:
        (?:sure|certainly|of\ course|okay|ok|alright|right|yes|yeah|got\ it)[!.,]*
      | (?:here(?:'|’)s|here\ is|here\ are|here\ they\ are|here\ you\ (?:go|are))
          (?:\s+(?:some|the|my|your))?
          (?:\s+(?:creative|requested|following))?
          (?:\s+(?:uses?|list|answers?|responses?))
          (?:\s+\w+){0,6}
      | uses?
    )\s*:?\s*$""",
    flags=re.I | re.X,
)


def _unwrap_fences_inplace(text):
    if "```" not in text:
        return text
    text = FENCE_RE.sub(lambda m: "\n" + (m.group(1) or "").strip() + "\n", text)
    text = UNCLOSED_FENCE_RE.sub(lambda m: "\n" + (m.group(1) or "").strip(), text)
    return text.replace("```", " ")


def _strip_leading_labels(text):
    """Drop chat preambles ('Here are some creative uses:') only.
    Require a following line so a lone use is never eaten.
    'Here is a doorstop' is a valid use and must be kept.
    """
    text = text.strip().strip("\"'`“”‘’")
    while True:
        lines = text.splitlines()
        if len(lines) < 2 or not AUT_PREAMBLE_LINE.match(lines[0]):
            break
        text = "\n".join(lines[1:]).strip()
    return text


def _chunks_from(text):
    chunks = re.split(r"[\n\r;]+", text)
    if len(chunks) == 1 and chunks[0].count(",") >= 3:
        chunks = re.split(r",\s*", chunks[0])
    out = []
    for chunk in chunks:
        chunk = AUT_ITEM_LABEL.sub("", chunk).strip().strip("\"'`“”‘’")
        chunk = re.sub(r"\s+", " ", chunk)
        if INLINE_ITEM.search(chunk):
            out.extend(p.strip() for p in INLINE_ITEM.split(chunk) if p.strip())
        elif chunk:
            out.append(chunk)
    return out


def parse(raw, cue=None, n_words=None, stim=None, **kwargs):
    """Raw AUT text + cue → {'cue', 'responses'} for evaluate(), or None.

    Parameters
    ----------
    raw : str
        Model or participant text.
    cue : str or sequence, optional
        The object (brick, paperclip, …). Required for SemDis. A sequence
        is joined with spaces so 'car tires' stays one cue.
    n_words : unused
        Accepted for API consistency. instruct() also accepts n_words
        without using it.
    stim : dict, optional
        Full instruct() return value. cue is read from stim['cue'] when
        cue is not passed.

    Returns
    -------
    dict or None
        {'cue': str, 'responses': list[str]} as evaluate() expects.
        None if the cue is missing or no use phrase was found.
    """
    if stim and cue is None:
        cue = stim.get("cue")
    if isinstance(cue, (list, tuple)):
        cue = " ".join(str(x) for x in cue if str(x).strip())
    cue = str(cue or "").strip()
    if not cue:
        return None

    text = _unwrap_fences_inplace(THINK_RE.sub(" ", str(raw or "")))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"^#+\s*.*$", "", text, flags=re.M)
    text = _strip_leading_labels(text)
    if not text:
        return None

    uses = []
    for chunk in _chunks_from(text):
        if len(chunk) < 2:
            continue
        if chunk.rstrip(":").lower() in {"use", "uses"}:
            continue
        uses.append(chunk)
    if not uses:
        return None
    return {"cue": cue, "responses": uses}
