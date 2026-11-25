"""Measures retrieval quality and latency on the sample documents.

Run from the project root:  python -m scripts.eval_retrieval
Runs on this machine with a temporary database; no API keys are needed.
"""

import json
import statistics
import tempfile
import time
from pathlib import Path

from packages.core.config import ROOT, get_settings
from packages.core.knowledge.embeddings import LocalEmbedder
from packages.core.knowledge.service import KnowledgeService
from packages.core.knowledge.store import KnowledgeStore

THRESHOLDS = (0.76, 0.78, 0.79, 0.80, 0.81, 0.82, 0.84)


def main() -> None:
    settings = get_settings()
    cases = json.loads((ROOT / "evals" / "retrieval.json").read_text())
    embedder = LocalEmbedder(settings.embedding_model)

    with tempfile.TemporaryDirectory() as folder:
        store = KnowledgeStore(Path(folder) / "eval.db")
        loader = KnowledgeService(store, embedder, min_score=0)
        passages = sum(
            loader.ingest(path.name, path.read_bytes())["chunks"]
            for path in sorted((ROOT / "data" / "sample").glob("*.md"))
        )
        total, unknown = len(cases["answerable"]), len(cases["unanswerable"])
        print(f"{passages} passages, {total} answerable and {unknown} unanswerable questions\n")
        print("threshold   correct in top 4   correct first   unanswerable rejected")
        for threshold in THRESHOLDS:
            service = KnowledgeService(store, embedder, min_score=threshold)
            top4 = first = 0
            for case in cases["answerable"]:
                found = [case["expect"] in p.content for p in service.search(case["q"])]
                top4 += any(found)
                first += bool(found) and found[0]
            rejected = sum(not service.search(q) for q in cases["unanswerable"])
            marker = "  <- configured" if threshold == settings.retrieval_min_score else ""
            print(
                f"{threshold:9.2f}   {top4:7d}/{total:<8d}   {first:5d}/{total:<7d}"
                f"   {rejected:9d}/{unknown}{marker}"
            )

        service = KnowledgeService(store, embedder, min_score=settings.retrieval_min_score)
        times = []
        for case in cases["answerable"]:
            started = time.perf_counter()
            service.search(case["q"])
            times.append((time.perf_counter() - started) * 1000)
        print(f"\nsearch latency: median {statistics.median(times):.0f} ms, worst {max(times):.0f} ms")

        print("\nmisses at the configured threshold:")
        for case in cases["answerable"]:
            if not any(case["expect"] in p.content for p in service.search(case["q"])):
                print("  not found:", case["q"])
        for question in cases["unanswerable"]:
            if found := service.search(question):
                print(f"  wrongly matched ({found[0].score:.3f}): {question}")


if __name__ == "__main__":
    main()
