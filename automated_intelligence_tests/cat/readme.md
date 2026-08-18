# CAT – Convergent Association Task

`instruct(n_items=10, seed=None)` returns instructions + unique word pairs.

`evaluate(responses)` scores the response JSON using average cosine similarity of the user word to the two cue words (via GWE). Higher = better convergent association.
