# AUT – Alternative Uses Task

`instruct(cue=None, n_words=None, seed=None)` returns instructions for generating creative uses of a common object.

- `cue` – the object. If omitted, one is sampled from the standard set (brick, paperclip, …).
- `n_words` – accepted for API consistency; currently unused.

`evaluate(responses, model_keys=None)` scores originality with SemDis (Beaty & Johnson, 2021).

`responses` is `{"cue": str, "responses": [str, ...]}`.

Each use is cleaned (lowercase, strip punctuation and numbers, drop `how="heavy"` stopwords, drop the cue and its simple plural). Leftover word vectors are multiplied slot by slot. Distance is `1 − cosine` between the cue vector and that composed vector. This is run in five spaces:

- `cbow-subs-300d`
- `cbow-ukwac-subs-300d`
- `cbow-baroni-400d`
- `tasa-lsa-300d`
- `glove-6b-300d`

The returned `score` is the mean of those five distances, then the mean across uses. `models` is each space on its own. `details` is one row per use. Higher = more original.

First call downloads the five spaces into `~/.cache/glove-word-embeddings`.