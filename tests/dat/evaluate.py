"""DAT evaluate: exact Olson scoring via GWE."""
import itertools
import re
import numpy as np
from glove_word_embeddings import mod, pre, val

def _cosine_dist(v1, v2):
    if v1 is None or v2 is None:
        return None
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return None
    return 1.0 - float(np.dot(v1, v2) / (n1 * n2))

def _embed(model, word):
    v = model.embed_exact(word)
    if v is not None:
        return v
    return model.embed_phrase(word)

def _word_index(key):
    m = re.search(r"(\d+)", str(key))
    return int(m.group(1)) if m else 0

def evaluate(responses, model_key="glove-840b-300d", minimum=7):
    """responses: list of words or dict {word_1: w, ...}."""
    if isinstance(responses, dict):
        keys = sorted(responses, key=_word_index)
        words = [str(responses[k]).strip() for k in keys]
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
        if cleaned not in uniques:
            uniques.append(cleaned)

    if len(uniques) < minimum:
        return {"score": None, "n_valid": len(uniques), "words": uniques}

    subset = uniques[:minimum]
    vecs = []
    for w in subset:
        v = _embed(model, w)
        if v is None:
            return {"score": None, "n_valid": len(uniques), "words": uniques}
        vecs.append(v)

    dists = [_cosine_dist(vecs[i], vecs[j])
             for i, j in itertools.combinations(range(len(vecs)), 2)
             if _cosine_dist(vecs[i], vecs[j]) is not None]
    if not dists:
        return {"score": None, "n_valid": len(uniques), "words": uniques}

    return {
        "score": float(sum(dists) / len(dists) * 100),
        "n_valid": len(uniques),
        "words": subset,
    }
