"""CWT evaluate: BERT DSI via GWE (Johnson et al., 2023)."""
import itertools
import re
import numpy as np
from glove_word_embeddings import mod


def _cosine_dist(v1, v2):
    if v1 is None or v2 is None:
        return None
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return None
    return 1.0 - float(np.dot(v1, v2) / (n1 * n2))


def _sentences(story):
    parts = re.split(r"(?<=[.!?])\s+", str(story).strip())
    return [p for p in parts if p]


def _token_vecs(sentence, model):
    torch = model._torch
    encoded = model.tokenizer(
        sentence, return_tensors="pt", truncation=True, max_length=512
    )
    with torch.no_grad():
        out = model.model(**encoded)
    vecs = []
    for layer in model.layers:
        tokens = out.hidden_states[layer][0][1:-1]
        for row in tokens:
            vecs.append(row.cpu().numpy().astype(np.float32))
    return vecs


def evaluate(responses, model_key="bert-large"):
    """responses: {"cue": [str, ...], "story": str}."""
    cue = responses.get("cue", [])
    story = str(responses.get("story", "")).strip()
    model = mod.load(model_key)
    vecs = []
    sents = _sentences(story)
    for sent in sents:
        vecs.extend(_token_vecs(sent, model))
    dists = []
    for a, b in itertools.combinations(vecs, 2):
        d = _cosine_dist(a, b)
        if d is not None:
            dists.append(d)
    return {
        "score": float(np.mean(dists)) if dists else None,
        "n_valid": len(vecs),
        "cue": cue,
        "n_sentences": len(sents),
        "n_pairs": len(dists),
        "model": model_key,
    }