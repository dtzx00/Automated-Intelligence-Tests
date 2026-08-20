# CAT – Convergent Association Task

`instruct(cue=None, single_item=False, n_words=10, seed=None)` returns instructions + word pairs.

- `n_words` – number of pairs to sample when `cue` is None (default 10).
- `cue` – optional explicit list of pairs (each a `(word_1, word_2)` tuple or a dict). Overrides sampling.
- `single_item=True` – return a single pair embedded in the instruction text.

`evaluate(responses)` scores the response JSON using average cosine similarity of the user word to the two cue words (via GWE). Higher = better convergent association.
