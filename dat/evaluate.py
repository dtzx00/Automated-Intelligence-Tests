"""DAT evaluate: exact Olson scoring via GWE."""
import itertools
import numpy as np
from glove_word_embeddings import mod, pre, val

def _cosine_dist(v1, v2):
    if v1 is None or v2 is None:
        return None
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return None
    return 1.0 - float(np.dot(v1, v2) / (n1 * n2))

def evaluate(responses, model_key="glove-840b-300d", minimum=7):
    """
    responses: list of words or dict {word_1: w, ...}
    Score = average pairwise cosine distance of first 7 unique valid words * 100.
    """
    if isinstance(responses, dict):
        words = [str(responses[k]).strip() for k in sorted(responses, key=lambda x: (len(x), x))]
    else:
        words = [str(w).strip() for w in responses]
    model = mod.load(model_key)
    uniques = []
    for w in words:
        cleaned = pre.clean_word(w)
        if not cleaned:
            continue
        if not (val.word(cleaned) or val.vocab(cleaned, model.vocab_set())):
            continue
        cand = cleaned
        if cand not in uniques:
            uniques.append(cand)
    if len(uniques) < minimum:
        return {"score": None, "n_valid": len(uniques), "words": uniques}
    subset = uniques[:minimum]
    vecs = []
    for w in subset:
        v = model.embed_exact(w) or model.embed_phrase(w)
        if v is None:
            return {"score": None, "n_valid": len(uniques), "words": uniques}
        vecs.append(v)
    dists = []
    for i, j in itertools.combinations(range(len(vecs)), 2):
        d = _cosine_dist(vecs[i], vecs[j])
        if d is not None:
            dists.append(d)
    if not dists:
        return {"score": None, "n_valid": len(uniques), "words": uniques}
    score = (sum(dists) / len(dists)) * 100.0
    return {"score": float(score), "n_valid": len(uniques), "words": subset}
