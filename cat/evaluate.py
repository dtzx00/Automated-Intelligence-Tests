"""CAT evaluate: proximity score using GWE."""
import numpy as np
from glove_word_embeddings import mod, pre, val

def _embed(model, word):
    v = model.embed_exact(word)
    if v is not None:
        return v
    return model.embed_phrase(word)

def _cosine_sim(v1, v2):
    if v1 is None or v2 is None:
        return None
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return None
    return float(np.dot(v1, v2) / (n1 * n2))

def evaluate(responses, model_key="glove-6b-300d"):
    """Score mean proximity of user word to the two cues (higher better).

    Accepts multi-item dict (wordset_*) or single-item dict (word_1/word_2/word_user).
    """
    if isinstance(responses, dict) and "word_user" in responses and "word_1" in responses:
        responses = {"wordset_1": responses}

    model = mod.load(model_key)
    scores, details = [], {}
    for key, item in responses.items():
        w1 = str(item.get("word_1", "")).strip().lower()
        w2 = str(item.get("word_2", "")).strip().lower()
        cleaned = pre.clean_word(str(item.get("word_user", "")).strip())
        if not cleaned or not (val.word(cleaned) or val.vocab(cleaned, model.vocab_set())):
            details[key] = {"valid": False, "score": None}
            continue
        s1 = _cosine_sim(_embed(model, cleaned), _embed(model, w1))
        s2 = _cosine_sim(_embed(model, cleaned), _embed(model, w2))
        if s1 is None or s2 is None:
            details[key] = {"valid": False, "score": None}
            continue
        item_score = (s1 + s2) / 2.0
        scores.append(item_score)
        details[key] = {"valid": True, "score": item_score, "cleaned": cleaned}
    return {
        "score": float(np.mean(scores)) if scores else None,
        "n_valid": len(scores),
        "details": details,
    }
