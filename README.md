# Automated Intelligence Tests

Minimal Python package providing automated tests of associative and creative ability for both humans and AI.

## Tests

| Test | Name                        | Status          |
|------|-----------------------------|-----------------|
| CAT  | Convergent Association Task | instruct + evaluate |
| DAT  | Divergent Association Task  | instruct + evaluate |
| AUT  | Alternative Uses Task       | instruct + placeholder evaluate |
| WRT  | Creative Writing Task       | instruct + placeholder evaluate |

## Install

```bash
pip install glove-word-embeddings numpy
# then clone / pip install -e .
# or once published: pip install automated-intelligence-tests
```

## Usage

```python
import automated_intelligence_tests as ait

# List all available tests (loads metadata.json from each test directory)
ait.list_available_tests()

# CAT
stim = ait.instruct("cat", n_items=10, seed=42)
score = ait.evaluate("cat", responses)

# DAT
stim = ait.instruct("dat")
score = ait.evaluate("dat", ["cat", "thimble", ...])

# AUT
stim = ait.instruct("aut")                 # or instruct("aut", object="brick")
# evaluate not yet implemented

# WRT
stim = ait.instruct("wrt")                 # or instruct("wrt", cues=["moon", "river", "whisper"])
# evaluate not yet implemented
```

See the individual `*/readme.md` files for details.

Depends only on `glove-word-embeddings` (for CAT/DAT) and numpy.
