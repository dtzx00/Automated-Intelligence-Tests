# Automated Intelligence Tests

Minimal Python package providing automated tests of associative and creative ability, for both human and artificial intelligence. Each test exposes the same three calls: `instruct()` builds the stimuli and prompt, `parse()` will do some simple automated parsing to fit the format of the scoring `evaluate()` function, and `evaluate()` scores the responses.

| Test  | Name                        | `instruct` | `evaluate`                                   |
|-------|-----------------------------|------------|----------------------------------------------|
| `cat` | Convergent Association Task | yes        | Semantic proximity score (Wang et al., WIP)  |
| `dat` | Divergent Association Task  | yes        | Semantic distance score (Olson et al., 2021) |
| `aut` | Alternative Uses Task       | yes        | SemDis originality (Beaty & Johnson, 2021)   |
| `cwt` | Creative Writing Task       | yes        | BERT DSI (Johnson et al., 2023)              |

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
ait.list_available_tests()
stim = ait.instruct("aut", cue="brick")
parsed = ait.parse("aut", raw, stim=stim)
result = ait.evaluate("aut", parsed)
```

`instruct()` returns a dict with `test`, `instructions`, `response_format`, and the test's own
stimuli. `evaluate()` returns a dict with `score` (`None` if nothing scorable), `n_valid`, and
per-test detail.

## API

```python
ait.list_available_tests()                   # short_name and long_name for every test
ait.instruct(test, **kwargs)                 # test in {"cat", "dat", "aut", "cwt"}
ait.call_test_instruction("DAT", **kwargs)   # same as instruct(), case-insensitive name
ait.parse(test, raw, stim=None)              # some basic automated parsing
ait.evaluate(test, responses, **kwargs)      # evaluate the scores using parsed response        
```

Sub-packages can also be used directly:
`from automated_intelligence_tests.cat import instruct, parse, evaluate`.

| Test  | `instruct` arguments                                 | `parse` arguments                          | `evaluate` arguments                     |
| ----- | ---------------------------------------------------- | ------------------------------------------ | ---------------------------------------- |
| `cat` | `cue=None, single_item=False, n_words=10, seed=None` | not implemented                            | `responses, model_key="glove-840b-300d"` |
| `dat` | `cue=None, n_words=10, seed=None`                    | `raw, cue=None, n_words=10, stim=None`     | `responses, model_key=..., minimum=7`    |
| `aut` | `cue=None, n_words=None, seed=None`                  | `raw, cue=None, n_words=None, stim=None`   | `responses, model_keys=None`             |
| `cwt` | `cue=None, n_words=3, seed=None`                     | `raw, cue=None, n_words=None, stim=None`   | `responses, model_key="bert-large"`      |

**CAT** samples word pairs from a fixed list of 8,069 English word pairs at cosine distance 0.85–0.95. `n_words` controls how many pairs are returned at once. Providing `cue=[(w1, w2), ...]` uses those explicit pairs (and a single pair automatically embeds it in the instruction text).

**DAT** asks for `n_words` words that are as different from each other as possible. Optional `cue` seeds the first word; the participant then supplies the remaining words.

**AUT** samples (or accepts) a common object via `cue`. `n_words` is accepted for API consistency but currently unused.

**CWT** samples (or accepts via `cue`) 1–3 cue words controlled by `n_words` and asks for a short creative story that incorporates every cue word.

## Scoring

- **CAT** — mean cosine *similarity* between the participant's word and each of the two cue words, averaged over items. Higher = stronger convergent association. Invalid or unembeddable words are marked `valid: False` and excluded rather than penalised.
- **DAT** — Olson's procedure exactly: mean pairwise cosine *distance* of the first 7 unique valid words, ×100. Returns `score: None` if fewer than 7 valid words are given.
- **AUT** — Beaty & Johnson SemDis: clean each use (`how="heavy"` stopwords, drop cue + plural), multiply leftover word vectors, take `1 − cosine` to the cue in five spaces (`cbow-subs-300d`, `cbow-ukwac-subs-300d`, `cbow-baroni-400d`, `tasa-lsa-300d`, `glove-6b-300d`). `score` is the mean of those spaces, then the mean across uses. Higher = more original. First call downloads the five spaces into `~/.cache/glove-word-embeddings`.
- **CWT** — Johnson et al. BERT DSI: split the story into sentences, keep BERT-large layers 6 and 7 for every real token, put those vectors in one list, take the mean pairwise `1 − cosine`. Higher = more divergent integration. First call downloads BERT into `~/.cache/glove-word-embeddings/huggingface`.

All will use [`glove-word-embeddings`](https://pypi.org/project/glove-word-embeddings/), default model `glove-840b-300d` for CAT and DAT. The first `evaluate()` call downloads the embedding file and caches it under `~/.cache/glove-word-embeddings`; later calls are offline. Other keys (`glove-6b-300d`, `wiki-news-300d-1m`, the `flair-olson-*` set, …) can be passed via `model_key`.

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
