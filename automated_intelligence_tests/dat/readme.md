# DAT – Divergent Association Task

`instruct(n_words=10)` returns the standard Olson-style instructions.

`evaluate(responses)` computes the DAT score exactly as Olson (average pairwise cosine distance of the first 7 unique valid words × 100) using GWE embeddings.
