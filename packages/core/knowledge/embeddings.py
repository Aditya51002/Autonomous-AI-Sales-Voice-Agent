"""Text embeddings. Replace this class to change the embedding model."""

from pathlib import Path
from typing import Protocol

import numpy as np

# Kept outside the project: the model is large and the project drive is NTFS.
CACHE_DIR = Path.home() / ".cache" / "fastembed"


class Embedder(Protocol):
    name: str

    def passages(self, texts: list[str]) -> np.ndarray: ...
    def query(self, text: str) -> np.ndarray: ...


def _normalise(vectors: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return (vectors / np.maximum(lengths, 1e-12)).astype(np.float32)


class LocalEmbedder:
    """Multilingual E5, run on this machine. Downloads about 2.2 GB on first use."""

    def __init__(self, model: str) -> None:
        from fastembed import TextEmbedding

        self.name = model
        self._model = TextEmbedding(model_name=model, cache_dir=str(CACHE_DIR))

    def passages(self, texts: list[str]) -> np.ndarray:
        # E5 models are trained with these prefixes.
        vectors = self._model.embed([f"passage: {text}" for text in texts], batch_size=16)
        return _normalise(np.array(list(vectors)))

    def query(self, text: str) -> np.ndarray:
        return _normalise(next(iter(self._model.embed([f"query: {text}"]))))
