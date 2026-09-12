# DAT – Divergent Association Task

- `instruct(cue=None, n_words=10, seed=None)` returns instructions for generating mutually distant words.
- `n_words` – how many words the participant should produce (default 10). 
- `cue` – optional starting word. When given, the instructions state that the first word is provided.
- `parse(raw, cue=None, n_words=10, stim=None)` parses a response string into a list of 10 nouns. 
- `evaluate(responses, model_key=..., minimum=7)` scores with Olson’s procedure (mean pairwise cosine distance of the first 7 unique valid words × 100).
