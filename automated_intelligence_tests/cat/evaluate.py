"""CAT evaluate: proximity score using GWE."""
import numpy as np
from glove_word_embeddings import mod, pre, val

def _cosine_sim(v1, v2):
    if v1 is None or v2 is None:
        return None
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return None
    return float(np.dot(v1, v2) / (n1 * n2))

def _embed(model, word):
    v = model.embed_exact(word)
    if v is not None:
        return v
    return model.embed_phrase(word)

def evaluate(responses, model_key="glove-840b-300d"):
    """responses: multi wordset dict or single {word_1, word_2, word_user}."""
    if "word_user" in responses and not any(k.startswith("wordset_") for k in responses):
        responses = {"wordset_1": responses}

    model = mod.load(model_key)
    scores, details = [], {}
    for key, item in responses.items():
        w1 = str(item.get("word_1", "")).strip().lower()
        w2 = str(item.get("word_2", "")).strip().lower()
        wu = str(item.get("word_user", "")).strip()
        cleaned = pre.clean_word(wu)
        if not cleaned or not val.word(cleaned):
            details[key] = {"valid": False, "score": None}
            continue
        v_user = _embed(model, cleaned)
        v1 = _embed(model, w1)
        v2 = _embed(model, w2)
        s1, s2 = _cosine_sim(v_user, v1), _cosine_sim(v_user, v2)
        if s1 is None or s2 is None:
            details[key] = {"valid": False, "score": None}
            continue
        score = (s1 + s2) / 2.0
        scores.append(score)
        details[key] = {"valid": True, "score": score, "cleaned": cleaned}
    return {
        "score": float(np.mean(scores)) if scores else None,
        "n_valid": len(scores),
        "details": details,
    }
