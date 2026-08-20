# CWT – Creative Writing Task

`instruct(cue=None, n_words=3, seed=None)` returns instructions for writing a short creative story that must include the provided cue word(s).

- If `cue` is omitted, a set of `n_words` (must be 1, 2 or 3) cues is sampled from the standard sets.
- The cue sets are taken from the divergent semantic integration (DSI) studies of Johnson et al. (2023).
- The returned dict always includes the chosen `cue` (and `n_words`) so evaluation has full context.
- `evaluate` is currently a placeholder (scoring not yet implemented; a future implementation could use DSI / BERT-based metrics from the same paper).

### Source
Johnson et al., (2023)
```
Johnson, D. R., Kaufman, J. C., Baker, B. S., Patterson, J. D., Barbot, B., Green, A. E., van Hell, J., Kennedy, E., Sullivan, G. F., Taylor, C. L., Ward, T., & Beaty, R. E. (2023). Divergent semantic integration (DSI): Extracting creativity from narratives with distributional semantic modeling. *Behavior Research Methods, 55*(7), 3726–3759. https://doi.org/10.3758/s13428-022-01986-2
```
