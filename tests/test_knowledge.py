"""Offline tests for document search. A word-counting embedder replaces the model."""

import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient
from livekit.agents import llm

from apps.agent.assistant import SalesAssistant
from apps.agent.retrieval import ApiRetriever, is_small_talk
from apps.api.knowledge import MAX_UPLOAD_BYTES, get_knowledge
from apps.api.main import app
from packages.core.config import Settings
from packages.core.knowledge.chunking import chunk_text
from packages.core.knowledge.parsing import DocumentError, extract_text
from packages.core.knowledge.service import KnowledgeService
from packages.core.knowledge.store import KnowledgeStore


class WordEmbedder:
    name = "words"

    def _vector(self, text):
        vector = np.zeros(512, dtype=np.float32)
        for word in text.lower().split():
            vector[zlib.crc32(word.strip(".,?!").encode()) % 512] += 1
        return vector / (np.linalg.norm(vector) or 1)

    def passages(self, texts):
        return np.stack([self._vector(t) for t in texts])

    def query(self, text):
        return self._vector(text)


DOC = b"""# Pricing

## Starter
The starter plan costs 499 rupees per month.

## Refunds
Refunds are available within fifteen days.
"""


@pytest.fixture
def knowledge(tmp_path):
    return KnowledgeService(KnowledgeStore(tmp_path / "k.db"), WordEmbedder(), min_score=0.2)


def test_chunks_carry_their_heading_path():
    chunks = chunk_text(DOC.decode())
    assert chunks[0].startswith("Pricing > Starter\n")
    assert chunks[1].startswith("Pricing > Refunds\n")


def test_long_text_is_split_without_losing_words():
    text = " ".join(f"word{i}." for i in range(1000))
    chunks = chunk_text(text, max_words=100)
    assert all(len(c.split()) <= 100 for c in chunks)
    assert " ".join(chunks).split() == text.split()


@pytest.mark.parametrize("name, data", [("a.exe", b"x"), ("a.pdf", b"junk"), ("a.txt", b"  ")])
def test_bad_files_are_rejected(name, data):
    with pytest.raises(DocumentError):
        extract_text(name, data)


def test_docx_headings_and_tables_are_read(tmp_path):
    import docx

    document = docx.Document()
    document.add_heading("Plans", level=1)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Starter", "499"
    path = tmp_path / "plans.docx"
    document.save(path)
    assert extract_text("plans.docx", path.read_bytes()) == "# Plans\n\nStarter | 499"


def test_search_ranks_the_right_passage_first(knowledge):
    knowledge.ingest("pricing.md", DOC)
    results = knowledge.search("how much does the starter plan cost per month")
    assert "499" in results[0].content and results[0].document == "pricing.md"


def test_unanswered_questions_are_logged_but_statements_are_not(knowledge):
    knowledge.ingest("pricing.md", DOC)
    assert knowledge.search("do you sell laptops?", call_id="c1") == []
    assert knowledge.search("zebra giraffe elephant") == []
    assert [g["question"] for g in knowledge.store.gaps("default")] == ["do you sell laptops?"]


def test_reupload_replaces_and_delete_removes(knowledge):
    knowledge.ingest("pricing.md", DOC)
    knowledge.ingest("pricing.md", b"The starter plan costs 599 rupees.")
    [document] = knowledge.store.documents("default")
    assert document["chunks"] == 1
    assert "599" in knowledge.search("starter plan costs")[0].content
    assert knowledge.store.delete_document("default", document["id"])
    assert knowledge.search("starter plan costs") == []
    assert knowledge.store.keyword_ranking("default", "starter", 5) == []


def test_tenants_cannot_see_each_other(knowledge):
    knowledge.ingest("pricing.md", DOC, tenant="a")
    assert knowledge.search("starter plan costs", tenant="b") == []
    assert knowledge.store.keyword_ranking("b", "starter", 5) == []


def test_hindi_keywords_and_search_syntax_are_safe(knowledge):
    knowledge.ingest("hi.txt", "शुरुआती योजना की कीमत 499 रुपये है".encode())
    assert knowledge.store.keyword_ranking("default", "कीमत", 5)
    knowledge.store.keyword_ranking("default", 'NEAR("a" OR * AND) -', 5)  # must not raise


def test_document_api(knowledge):
    app.dependency_overrides[get_knowledge] = lambda: knowledge
    try:
        client = TestClient(app)
        upload = client.post("/documents", files={"file": ("../../pricing.md", DOC)})
        assert upload.status_code == 201 and upload.json()["name"] == "pricing.md"
        found = client.post("/search", json={"query": "starter plan costs"}).json()
        assert "499" in found["passages"][0]["content"]
        too_big = {"file": ("big.txt", b"a" * (MAX_UPLOAD_BYTES + 1))}
        assert client.post("/documents", files=too_big).status_code == 413
        assert client.post("/documents", files={"file": ("x.exe", b"x")}).status_code == 400
        foreign = {"Origin": "https://evil.example"}
        assert client.get("/documents", headers=foreign).status_code == 403
        document_id = upload.json()["id"]
        assert client.delete(f"/documents/{document_id}").status_code == 204
        assert client.get("/documents").json() == []
    finally:
        app.dependency_overrides.clear()


# --- agent side ---


def settings():
    return Settings(_env_file=None)


def context(*turns):
    chat_ctx = llm.ChatContext.empty()
    for role, text in turns:
        chat_ctx.add_message(role=role, content=text)
    return chat_ctx


async def test_passages_are_added_without_changing_history():
    queries, shown = [], []

    async def retrieve(query):
        queries.append(query)
        return [{"document": "pricing.md", "content": "Starter costs 499", "score": 0.9}]

    assistant = SalesAssistant(settings(), retrieve=retrieve, on_sources=shown.append)
    history = context(("user", "How much is the starter plan per month?"))

    grounded = await assistant.prepare_turn(history)
    await assistant.prepare_turn(history)

    text = grounded.items[-1].text_content
    assert "Starter costs 499" in text and text.endswith("per month?")
    assert history.items[-1].text_content == "How much is the starter plan per month?"
    assert len(queries) == 1  # the repeat used the cached result
    assert shown[0][0]["document"] == "pricing.md"


async def test_short_follow_up_searches_with_previous_question():
    queries = []

    async def retrieve(query):
        queries.append(query)
        return []

    assistant = SalesAssistant(settings(), retrieve=retrieve)
    history = context(
        ("user", "What does the growth plan cost?"),
        ("assistant", "It is 1499."),
        ("user", "and yearly?"),
    )
    grounded = await assistant.prepare_turn(history)
    assert queries == ["What does the growth plan cost? and yearly?"]
    assert "No relevant passage" in grounded.items[-1].text_content


async def test_small_talk_and_failed_search():
    async def fail(query):
        return None

    assistant = SalesAssistant(settings(), retrieve=fail)
    thanks = await assistant.prepare_turn(context(("user", "ok thank you")))
    assert "Reference passages" not in thanks.items[-1].text_content
    asked = await assistant.prepare_turn(context(("user", "price?")))
    assert "No relevant passage" in asked.items[-1].text_content


@pytest.mark.parametrize(
    "question, instruction",
    [
        ("We make invoices by hand", "Reply in English only."),
        ("हम हाथ से बिल बनाते हैं", "Reply in Hindi"),
        ("हमारी team manually invoice बनाती है", "Reply in Hinglish"),
    ],
)
async def test_reply_language_is_stated_for_each_turn(question, instruction):
    assistant = SalesAssistant(settings())
    prepared = await assistant.prepare_turn(context(("user", question)))
    assert instruction in prepared.items[-1].text_content
    assert assistant.language.value == "english"  # unchanged until the turn is confirmed


def test_small_talk_detection():
    assert is_small_talk("हाँ ठीक है")
    assert not is_small_talk("price?")


async def test_unreachable_api_returns_none():
    retriever = ApiRetriever("http://127.0.0.1:9", timeout=0.5)
    try:
        assert await retriever("price") is None
    finally:
        await retriever.aclose()
