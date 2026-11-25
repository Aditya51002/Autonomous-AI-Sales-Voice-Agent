"""Document upload and search endpoints."""

import threading
from functools import lru_cache
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from packages.core.config import Settings, get_settings
from packages.core.knowledge.embeddings import LocalEmbedder
from packages.core.knowledge.parsing import DocumentError
from packages.core.knowledge.service import DEFAULT_TENANT, KnowledgeService
from packages.core.knowledge.store import KnowledgeStore

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_loading = threading.Lock()


@lru_cache
def _build_service() -> KnowledgeService:
    settings = get_settings()
    return KnowledgeService(
        KnowledgeStore(settings.knowledge_db),
        LocalEmbedder(settings.embedding_model),
        min_score=settings.retrieval_min_score,
    )


def get_knowledge() -> KnowledgeService:
    # The lock stops two requests loading the model at the same time.
    with _loading:
        return _build_service()


def trusted_origin(
    settings: Annotated[Settings, Depends(get_settings)],
    origin: Annotated[str | None, Header()] = None,
) -> None:
    """Stop other websites open in the browser from calling the local API."""
    if origin is not None and origin != settings.web_origin:
        raise HTTPException(403, "Requests from this origin are not allowed.")


Knowledge = Annotated[KnowledgeService, Depends(get_knowledge)]
router = APIRouter(dependencies=[Depends(trusted_origin)])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    call_id: str | None = Field(default=None, max_length=100)


@router.post("/documents", status_code=201)
def upload_document(file: UploadFile, knowledge: Knowledge) -> dict:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is larger than 5 MB.")
    # Only the base name is kept; the original file is not saved to disk.
    name = PurePath(file.filename or "document.txt").name
    try:
        return knowledge.ingest(name, data)
    except DocumentError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/documents")
def list_documents(knowledge: Knowledge) -> list[dict]:
    return knowledge.store.documents(DEFAULT_TENANT)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, knowledge: Knowledge) -> None:
    if not knowledge.store.delete_document(DEFAULT_TENANT, document_id):
        raise HTTPException(404, "Document not found.")


@router.post("/search")
def search(request: SearchRequest, knowledge: Knowledge) -> dict:
    passages = knowledge.search(request.query, call_id=request.call_id)
    return {"passages": [passage.as_dict() for passage in passages]}


@router.get("/knowledge-gaps")
def knowledge_gaps(knowledge: Knowledge) -> list[dict]:
    return knowledge.store.gaps(DEFAULT_TENANT)
