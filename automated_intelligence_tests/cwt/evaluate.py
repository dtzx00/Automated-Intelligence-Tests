"""CWT evaluate – placeholder.

Scoring for creative writing is not yet implemented.
Typical approaches involve human ratings of creativity, originality, coherence,
or automated metrics such as Divergent Semantic Integration (DSI) based on
embedding novelty / linguistic features (see Johnson et al., 2023).
"""

def evaluate(responses, **kwargs):
    """Placeholder. Will later score creativity of the generated story (possibly via DSI)."""
    raise NotImplementedError(
        "CWT evaluation is not yet implemented. "
        "Provide the story text (or the response dict from instruct) once scoring is ready."
    )