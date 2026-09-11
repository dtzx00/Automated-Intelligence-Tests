"""CWT parse: raw model or human text → ait.evaluate('cwt', ...) input.

Johnson, D. R., Kaufman, J. C., Baker, B. S., Patterson, J. D., Barbot, B.,
Green, A. E., van Hell, J. G., Kennedy, E., Sullivan, G. F., Taylor, C. L.,
Ward, T. B., & Beaty, R. E. (2023). Divergent semantic integration (DSI):
Extracting creativity from narratives with distributional semantic modeling.
Behavior Research Methods, 55, 3726–3759.

This module only unwraps LLM wrappers (fences, Title:/heading lines,
<think> blocks) and attaches the cue list. Johnson et al. leave the story
almost untouched — 'nothing (except some special characters) was removed'
before embeddings. Sentence splitting, BERT-large layers 6–7, and mean
pairwise 1 − cosine live in evaluate.py. Do not fold those into parse.
"""
from __future__ import annotations

import re

FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*?)\n?```", flags=re.S)
UNCLOSED_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n?(.*)$", flags=re.S)
THINK_RE = re.compile(
    r"<(?:think|thinking|reasoning)>.*?</(?:think|thinking|reasoning)>",
    flags=re.S | re.I,
)


def _unwrap_fences(text, first=False):
    if "```" not in text:
        return text
    chunks = [m.group(1).strip() for m in FENCE_RE.finditer(text) if m.group(1).strip()]
    if chunks:
        return chunks[0] if first else "\n".join(chunks)
    m = UNCLOSED_FENCE_RE.search(text)
    return m.group(1).strip() if m else text


def parse(raw, cue=None, n_words=None, stim=None, **kwargs):
    """Raw CWT text + cue → {'cue', 'story'} for evaluate(), or None.

    Parameters
    ----------
    raw : str
        Model or participant story text.
    cue : list[str] or str, optional
        Cue words the story was asked to include. A string is split on
        commas/whitespace. evaluate() scores the story; cue is passed
        through to match the evaluate() contract.
    n_words : unused
        Accepted for API consistency.
    stim : dict, optional
        Full instruct() return value. cue is read from stim['cue'] when
        cue is not passed.

    Returns
    -------
    dict or None
        {'cue': list[str], 'story': str} as evaluate() expects.
        None if the story is empty after wrapper stripping.
    """
    if stim and cue is None:
        cue = stim.get("cue")
    if cue is None:
        cue = []
    elif isinstance(cue, str):
        cue = [w for w in re.split(r"[,\s]+", cue) if w]
    else:
        cue = [str(w).strip() for w in cue if str(w).strip()]

    text = _unwrap_fences(THINK_RE.sub(" ", str(raw or "")), first=True)
    text = re.sub(r"^#+\s*.*$", "", text, flags=re.M)
    text = re.sub(r"^\s*Title:.*$", "", text, flags=re.M | re.I)
    text = re.sub(
        r"^\s*(Here(?:'|’)s (?:a |the )?story|Story)\s*:\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return None
    return {"cue": cue, "story": text}
