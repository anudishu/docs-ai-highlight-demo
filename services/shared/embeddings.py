from __future__ import annotations

import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from shared.config import EMBEDDING_MODEL, GCP_PROJECT, VERTEX_LOCATION

_model: TextEmbeddingModel | None = None


def _get_model() -> TextEmbeddingModel:
    global _model
    if _model is None:
        vertexai.init(project=GCP_PROJECT, location=VERTEX_LOCATION)
        _model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    inputs = [TextEmbeddingInput(text=t, task_type="RETRIEVAL_DOCUMENT") for t in texts]
    batch_size = 16
    vectors: list[list[float]] = []
    for i in range(0, len(inputs), batch_size):
        batch = inputs[i : i + batch_size]
        result = model.get_embeddings(batch)
        vectors.extend([item.values for item in result])
    return vectors


def embed_query(text: str) -> list[float]:
    model = _get_model()
    result = model.get_embeddings(
        [TextEmbeddingInput(text=text, task_type="RETRIEVAL_QUERY")]
    )
    return result[0].values
