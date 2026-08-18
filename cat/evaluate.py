"""CAT evaluate: proximity score using GWE."""
import numpy as np
from glove_word_embeddings import mod, pre, val

def _cosine_sim(v1, v2):
    if v1 is None or v2 is None:
        return None
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return None
    return float(np.dot(v1, v2) / (n1 * n2))

def evaluate(responses, model_key="glove-840b-300d"):
    """
    responses: {"wordset_1": {"word_1":.., "word_2":.., "word_user":..}, ...}
             or a single {"word_1":.., "word_2":.., "word_user":..} when single_item was used.
    Returns score (mean proximity of user word to the two cues), higher better.
    """
    # Normalise single-item response into the multi-item shape
    if "word_user" in responses and "wordset_" not in str(responses.keys()):
        responses = {"wordset_1": responses}

    model = mod.load(model_key)
    scores = []
    details = {}
    for key, item in responses.items():
        w1 = str(item.get("word_1", "")).strip().lower()
        w2 = str(item.get("word_2", "")).strip().lower()
        wu = str(item.get("word_user", "")).strip()
        cleaned = pre.clean_word(wu)
        if not cleaned or not val.word(cleaned):
            details[key] = {"valid": False, "score": None, "reason": "invalid or not in Olson list"}
            continue
        v_user = model.embed_exact(cleaned) or model.embed_phrase(cleaned)
        v1 = model.embed_exact(w1) or model.embed_phrase(w1)
        v2 = model.embed_exact(w2) or model.embed_phrase(w2)
        s1 = _cosine_sim(v_user, v1)
        s2 = _cosine_sim(v_user, v2)
        if s1 is None or s2 is None:
            details[key] = {"valid": False, "score": None, "reason": "missing embedding"}
            continue
        item_score = (s1 + s2) / 2.0
        scores.append(item_score)
        details[key] = {"valid": True, "score": item_score, "cleaned": cleaned}
    overall = float(np.mean(scores)) if scores else None
    return {"score": overall, "n_valid": len(scores), "details": details}
