"""AUT evaluate: SemDis originality via GWE (Beaty & Johnson, 2021)."""
import re
import numpy as np
from glove_word_embeddings import mod, pre

SPACES = [
    "cbow-subs-300d",
    "cbow-ukwac-subs-300d",
    "cbow-baroni-400d",
    "tasa-lsa-300d",
    "glove-6b-300d"]


def _cosine_dist(v1, v2):
    if v1 is None or v2 is None:
        return None
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return None
    return 1.0 - float(np.dot(v1, v2) / (n1 * n2))


def _words(text):
    text = pre.strip_marks(str(text)).lower()
    text = re.sub(r"\d+", " ", text)
    return pre.remove_stopwords(text, how="heavy")


def _tokens(use, cue):
    drop = set()
    for w in _words(cue):
        drop.update((w, w + "s"))
    return [w for w in _words(use) if w not in drop]


def _compose(tokens, model):
    vecs = [model.embed_exact(w) for w in tokens]
    vecs = [v for v in vecs if v is not None]
    if not vecs:
        return None
    out = vecs[0]
    for v in vecs[1:]:
        out = out * v
    return out


def _score_use_in_space(tokens, cue, model):
    return _cosine_dist(_compose(_words(cue), model),
                        _compose(tokens, model))


def evaluate(responses, model_keys=None):
    """responses: {"cue": str, "responses": [str, ...]}."""
    cue = str(responses.get("cue", "")).strip().lower()
    uses = [str(u) for u in responses.get("responses", [])]
    keys = list(model_keys) if model_keys is not None else list(SPACES)
    models = {key: mod.load(key) for key in keys}

    details = []
    use_scores = []
    space_scores = {key: [] for key in keys}

    for use in uses:
        tokens = _tokens(use, cue)
        per_space = {}
        for key, model in models.items():
            dist = _score_use_in_space(tokens, cue, model)
            per_space[key] = dist
            if dist is not None:
                space_scores[key].append(dist)
        usable = [d for d in per_space.values() if d is not None]
        use_score = float(np.mean(usable)) if usable else None
        details.append({
            "use": use,
            "tokens": tokens,
            "score": use_score,
            "models": per_space,
        })
        if use_score is not None:
            use_scores.append(use_score)

    return {
        "score": float(np.mean(use_scores)) if use_scores else None,
        "n_valid": len(use_scores),
        "cue": cue,
        "models": {
            key: (float(np.mean(vals)) if vals else None)
            for key, vals in space_scores.items()
        },
        "details": details,
    }
