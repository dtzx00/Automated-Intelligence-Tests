# CWT – Creative Writing Task

- `instruct(cue=None, n_words=3, seed=None)` returns instructions for writing a short creative story.
- If `cue` is omitted, a set of `n_words` (must be 1, 2 or 3) cues is sampled from the standard sets.
- The cue sets are taken from Johnson et al. (2023).
- The returned dict includes `cue` and `n_words` so evaluation has full context.
- `parse(raw, cue=None, n_words=None, stim=None)` lightly parses story to fit evaluate format. 
- `evaluate(responses, model_key="bert-large")` scores the story with BERT DSI (Johnson et al., 2023).
- `responses` is `{"cue": [str, ...], "story": str}`.

The story is split into sentences. BERT-large reads each sentence and keeps layers 6 and 7 for every real token. Those vectors go into one list. DSI is the mean pairwise `1 − cosine` on that list (DAT-style, not cue-vs-story). Higher = more divergent integration.

Returns `score`, `n_valid` (list size), `n_sentences`, `n_pairs`, `cue`, and `model`. First call downloads BERT into `~/.cache/glove-word-embeddings/huggingface`.

### Source
Johnson, D. R., Kaufman, J. C., Baker, B. S., Patterson, J. D., Barbot, B., Green, A. E., van Hell, J., Kennedy, E., Sullivan, G. F., Taylor, C. L., Ward, T., & Beaty, R. E. (2023). Divergent semantic integration (DSI): Extracting creativity from narratives with distributional semantic modeling. *Behavior Research Methods, 55*(7), 3726–3759. https://doi.org/10.3758/s13428-022-01986-2
