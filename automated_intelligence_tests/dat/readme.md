# DAT – Divergent Association Task

- `instruct(cue=None, n_words=10, seed=None)` returns instructions for generating mutually distant words.
- `n_words` – how many words the participant should produce (default 10). 
- `cue` – optional starting word. When given, the instructions state that the first word is provided.
- `parse(raw, cue=None, n_words=10, stim=None)` parses a response string into a list of 10 nouns. 
- `evaluate(responses, model_key=..., minimum=7)` scores with Olson’s procedure (mean pairwise cosine distance of the first 7 unique valid words × 100).

### Citations

`Olson, J. A., Nahas, J., Chmoulevitch, D., Cropper, S. J., & Webb, M. E. (2021). Naming unrelated words predicts creativity. Proceedings of the National Academy of Sciences, 118(25), e2022340118. https://doi.org/10.1073/pnas.2022340118`

`Wang, D., Huang, D., Shen, H., & Uzzi, B. (2026). A large-scale comparison of divergent creativity in humans and large language models. Nature Human Behaviour, 10(3), 531–540. https://doi.org/10.1038/s41562-025-02331-1`
