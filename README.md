# Automated Intelligence Tests

Minimal Python package providing automated CAT (Convergent Association Task) and DAT (Divergent Association Task) for both humans and AI.

## Install

```bash
pip install glove-word-embeddings
# then clone / pip install -e .
```

## Usage

```python
import automated_intelligence_tests as ait

# CAT
stim = ait.instruct("cat", n_items=10, seed=42)
print(stim["instructions"])
print(stim["items"])
# subject produces responses in the response_format
score = ait.evaluate("cat", responses)

# DAT
stim = ait.instruct("dat")
score = ait.evaluate("dat", ["cat", "thimble", ...])
```

See `cat/readme.md` and `dat/readme.md`.

Depends only on `glove-word-embeddings` for validation and embeddings.
