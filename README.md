# Automated Intelligence Tests

Minimal Python package providing automated tests of associative and creative ability, for both
human and artificial intelligence. Each test exposes the same two calls: `instruct()` builds the
stimuli and prompt, `evaluate()` scores the responses.

| Test  | Name                        | `instruct` | `evaluate`                        |
|-------|-----------------------------|------------|-----------------------------------|
| `cat` | Convergent Association Task | yes        | Semantic proximity score (GloVe)  |
| `dat` | Divergent Association Task  | yes        | Semantic distance score (GloVe)   |
| `aut` | Alternative Uses Task       | yes        | not implemented yet               |
| `cwt` | Creative Writing Task       | yes        | not implemented yet               |

## Install

```bash
pip install git+https://github.com/dtzx00/Automated-Intelligence-Tests.git
```

Once published to PyPI: `pip install automated-intelligence-tests`.

Dependencies (`glove-word-embeddings`, `numpy`) are declared in `pyproject.toml` and installed
automatically — no separate requirements step. Python 3.9+.

For local development:

```bash
git clone https://github.com/dtzx00/Automated-Intelligence-Tests.git
cd Automated-Intelligence-Tests
pip install -e .
```

## Quickstart

```python
import automated_intelligence_tests as ait

ait.list_available_tests()        # {"CAT": "Convergent Association Task", ...}

# 1. Build the stimuli and prompt
task = ait.instruct("cat", n_words=10, seed=42)
print(task["instructions"])       # give this to a person or a model
print(task["response_format"])    # the shape the answer should come back in

# 2. Fill in "word_user" for each item, then score
responses = {
    "wordset_1": {"word_1": "television", "word_2": "lake", "word_user": "reflection"},
    # ...
}
result = ait.evaluate("cat", responses)
print(result["score"], result["n_valid"])
```

`instruct()` returns a dict with `test`, `instructions`, `response_format`, and the test's own
stimuli. `evaluate()` returns a dict with `score` (`None` if nothing scorable), `n_valid`, and
per-test detail.

## API

```python
ait.list_available_tests()               # -> {short_name: long_name} for every test
ait.instruct(test, **kwargs)             # test in {"cat", "dat", "aut", "cwt"}
ait.call_test_instruction("DAT", **kwargs)   # same as instruct(), case-insensitive name
ait.evaluate(test, responses, **kwargs)
```

Sub-packages can also be used directly:
`from automated_intelligence_tests.cat import instruct, evaluate`.

| Test  | `instruct` arguments                       | `evaluate` arguments                     |
|-------|--------------------------------------------|------------------------------------------|
| `cat` | `single_item=False, n_words=10, seed=None` | `responses, model_key="glove-840b-300d"` |
| `dat` | `n_words=10`                               | `responses, model_key=..., minimum=7`    |
| `aut` | `cue=None, seed=None`                      | raises `NotImplementedError`             |
| `cwt` | `cue=None, n_words=3, seed=None`           | raises `NotImplementedError`             |

**CAT** samples word pairs from a fixed list of 8,069 English word pairs at cosine distance 0.85–0.95, the
instrument's difficulty control. No word repeats within an assessment. `single_item=True` returns
one pair with the pair embedded in the instruction text, for one-call-per-item delivery.

**DAT** takes either a list of words or a `{"word_1": ..., ...}` dict.

**AUT** samples a common object (brick, paperclip, …) unless one is given via `cue`.

**CWT** samples one to three cue words (controlled by `n_words`) unless they are given via `cue`.

## Scoring

- **CAT** — mean cosine *similarity* between the participant's word and each of the two cue words,
  averaged over items. Higher = stronger convergent association. Invalid or unembeddable words are
  marked `valid: False` and excluded rather than penalised.
- **DAT** — Olson's procedure exactly: mean pairwise cosine *distance* of the first 7 unique valid
  words, ×100. Returns `score: None` if fewer than 7 valid words are given.

Both use [`glove-word-embeddings`](https://pypi.org/project/glove-word-embeddings/), default model
`glove-840b-300d`. The first `evaluate()` call downloads the embedding file and caches it under
`~/.cache/glove-word-embeddings`; later calls are offline. Other keys (`glove-6b-300d`,
`wiki-news-300d-1m`, the `flair-olson-*` set, …) can be passed via `model_key`.

## Layout

```
automated_intelligence_tests/
    __init__.py          dispatcher: list_available_tests() / instruct() / evaluate()
    cat/  dat/           per test: instruct.py, evaluate.py, metadata.json,
    aut/  cwt/                     readme.md, example.ipynb
    cat/data/cat_word_pairs_en.txt CAT word-pair list
```

Each test folder carries a `metadata.json` holding its short name, long name and description.
That file is what `list_available_tests()` reads, so dropping in a new test folder with one makes
it discoverable automatically. Each also has its own `readme.md` and a runnable `example.ipynb`.

## License

MIT
