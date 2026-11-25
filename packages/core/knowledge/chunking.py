"""Splits text into passages that keep their heading for context."""

import re

# About 250 words stays well inside the embedding model's 512-token input.
MAX_WORDS = 220

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")


def chunk_text(text: str, max_words: int = MAX_WORDS) -> list[str]:
    chunks: list[str] = []
    headings: dict[int, str] = {}
    body: list[str] = []

    def flush() -> None:
        if not body:
            return
        title = " > ".join(headings[level] for level in sorted(headings))
        for part in _pack(body, max_words):
            chunks.append(f"{title}\n{part}" if title else part)
        body.clear()

    for block in re.split(r"\n\s*\n", text):
        lines: list[str] = []
        for line in block.strip().splitlines():
            if match := _HEADING.match(line.strip()):
                if lines:
                    body.append("\n".join(lines))
                    lines = []
                flush()
                level = len(line.strip()) - len(line.strip().lstrip("#"))
                headings = {k: v for k, v in headings.items() if k < level}
                headings[level] = match.group(1).strip()
            elif line.strip():
                lines.append(line.strip())
        if lines:
            body.append("\n".join(lines))
    flush()
    return chunks


def _pack(blocks: list[str], max_words: int) -> list[str]:
    """Join blocks up to the word limit, splitting any block that is too long."""
    pieces: list[str] = []
    for block in blocks:
        if len(block.split()) <= max_words:
            pieces.append(block)
            continue
        for sentence in _SENTENCE_END.split(block):
            words = sentence.split()
            pieces.extend(
                " ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)
            )

    packed: list[str] = []
    size = 0
    for piece in pieces:
        length = len(piece.split())
        if packed and size + length <= max_words:
            packed[-1] += "\n" + piece
            size += length
        else:
            packed.append(piece)
            size = length
    return packed
