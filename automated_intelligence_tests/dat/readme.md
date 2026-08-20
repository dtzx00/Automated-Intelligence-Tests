# DAT – Divergent Association Task

`instruct(cue=None, n_words=10, seed=None)` returns instructions for generating mutually distant words.

- `n_words` – how many words the participant should produce (default 10). The number appears in the instruction text and in the response format keys.
- `cue` – optional starting word. When given, the instructions state that the first word is provided and `response_format["word_1"]` is pre-filled with that cue.

`evaluate(responses, model_key=..., minimum=7)` scores with Olson’s procedure (mean pairwise cosine distance of the first 7 unique valid words × 100).
