"""Turns an uploaded file into text, marking headings with Markdown '#'."""

import io
from pathlib import PurePath

SUPPORTED = (".pdf", ".docx", ".md", ".txt")


class DocumentError(ValueError):
    """The file cannot be used. The message is safe to show to the uploader."""


def extract_text(filename: str, data: bytes) -> str:
    suffix = PurePath(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise DocumentError(f"Unsupported file type. Use {', '.join(SUPPORTED)}.")
    try:
        if suffix == ".pdf":
            text = _pdf(data)
        elif suffix == ".docx":
            text = _docx(data)
        else:
            text = data.decode("utf-8-sig")
    except DocumentError:
        raise
    except Exception as error:
        raise DocumentError("The file could not be read. Is it damaged or encrypted?") from error
    if not text.strip():
        raise DocumentError("No text found. Scanned documents need OCR first.")
    return text


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader

    return "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def _docx(data: bytes) -> str:
    from docx import Document
    from docx.table import Table

    lines = []
    for block in Document(io.BytesIO(data)).iter_inner_content():
        if isinstance(block, Table):
            for row in block.rows:
                lines.append(" | ".join(cell.text.strip() for cell in row.cells))
        elif block.text.strip():
            style = block.style.name if block.style else ""
            prefix = "# " if style.startswith(("Heading", "Title")) else ""
            lines.append(prefix + block.text.strip())
    return "\n\n".join(lines)
