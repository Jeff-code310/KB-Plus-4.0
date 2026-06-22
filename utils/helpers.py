import os

from constants import BINARY_EXTENSIONS, FILE_ICONS


def format_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def get_file_icon(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return FILE_ICONS.get(ext, "\U0001F4C4")


def is_text_file(filepath: str) -> bool:
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".docx", ".pdf", ".xlsx", ".xls", ".pptx"):
        return True
    return ext not in BINARY_EXTENSIONS


def _read_docx_text(filepath: str, max_chars: int = 65536) -> str | None:
    try:
        from docx import Document
        doc = Document(filepath)
        text = "\n".join(p.text for p in doc.paragraphs)
        return text[:max_chars]
    except Exception:
        return None


def _read_pdf_text(filepath: str, max_chars: int = 65536) -> str | None:
    try:
        import fitz
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text()
            if len(text) >= max_chars:
                break
        doc.close()
        return text[:max_chars]
    except Exception:
        return None


def read_file_chunk(filepath: str, max_bytes: int = 65536) -> str | None:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".docx":
        return _read_docx_text(filepath, max_bytes)
    if ext == ".pdf":
        return _read_pdf_text(filepath, max_bytes)
    if ext in (".xlsx", ".xls", ".pptx"):
        from services.document_parser import parse_document
        try:
            doc = parse_document(filepath)
            return doc.text_content[:max_bytes]
        except Exception:
            return None
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_bytes)
    except Exception:
        return None
