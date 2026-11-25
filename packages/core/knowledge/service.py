"""Ingests documents and answers searches (hybrid: meaning plus keywords)."""

import re
from dataclasses import asdict, dataclass

import numpy as np

from packages.core.knowledge.chunking import chunk_text
from packages.core.knowledge.embeddings import Embedder
from packages.core.knowledge.parsing import DocumentError, extract_text
from packages.core.knowledge.store import KnowledgeStore

DEFAULT_TENANT = "default"
MAX_CHUNKS = 500
_CANDIDATES = 20
_RRF_K = 60  # standard constant for reciprocal rank fusion

_QUESTION = re.compile(
    r"\?|\b(?:what|how|why|when|where|which|who|can|could|do|does|is|are|will|"
    r"kya|kitna|kitne|kitni|kaise|kab|kahan|kaun)\b|क्या|कितन|कैसे|कब|कहाँ|कहां|कौन|क्यों",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Passage:
    document: str
    content: str
    score: float  # cosine similarity between question and passage

    def as_dict(self) -> dict:
        return asdict(self)


class KnowledgeService:
    def __init__(
        self, store: KnowledgeStore, embedder: Embedder, min_score: float, top_k: int = 4
    ) -> None:
        self.store = store
        self._embedder = embedder
        self._min_score = min_score
        self._top_k = top_k

    def ingest(self, filename: str, data: bytes, tenant: str = DEFAULT_TENANT) -> dict:
        chunks = chunk_text(extract_text(filename, data))
        if not chunks:
            raise DocumentError("No text passages found in the file.")
        if len(chunks) > MAX_CHUNKS:
            raise DocumentError(f"The document is too long (limit {MAX_CHUNKS} passages).")
        vectors = self._embedder.passages(chunks)
        document_id = self.store.replace_document(
            tenant, filename, self._embedder.name, chunks, vectors
        )
        return {"id": document_id, "name": filename, "chunks": len(chunks)}

    def search(
        self, query: str, tenant: str = DEFAULT_TENANT, call_id: str | None = None
    ) -> list[Passage]:
        """The best passages, or none. An unanswered question is logged as a gap."""
        chunks, vectors = self.store.vectors(tenant, self._embedder.name)
        passages = self._rank(query, tenant, chunks, vectors) if chunks else []
        if not passages and _QUESTION.search(query):
            self.store.add_gap(tenant, query, call_id)
        return passages

    def _rank(self, query, tenant, chunks, vectors: np.ndarray) -> list[Passage]:
        scores = vectors @ self._embedder.query(query)
        by_meaning = [chunks[i].id for i in np.argsort(-scores)[:_CANDIDATES]]
        by_keyword = self.store.keyword_ranking(tenant, query, _CANDIDATES)

        fused: dict[int, float] = {}
        for ranking in (by_meaning, by_keyword):
            for position, chunk_id in enumerate(ranking):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (_RRF_K + position + 1)

        index = {chunk.id: i for i, chunk in enumerate(chunks)}
        results = []
        for chunk_id in sorted(fused, key=fused.get, reverse=True):
            i = index.get(chunk_id)
            # A shared keyword alone is not enough: the meaning must also be close.
            if i is None or scores[i] < self._min_score:
                continue
            results.append(Passage(chunks[i].document, chunks[i].content, float(scores[i])))
            if len(results) == self._top_k:
                break
        return results
