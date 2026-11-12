"""Storing uploaded resumes/cover letters and reading the text out of them.

Files go in DATA_DIR/documents under a random name (never the name you uploaded),
so a strange file name can't overwrite anything. The extracted text is saved in
the database; that's what fit checks read.

Only PDF and Word (.docx) are accepted, and the first bytes of the file are
checked to make sure it really is one (a renamed .exe won't pass).
"""
import io
import secrets
from pathlib import Path

import config

MAX_BYTES = 10 * 1024 * 1024          # 10 MB
ALLOWED = {".pdf": b"%PDF", ".docx": b"PK\x03\x04"}   # file type -> how such a file starts


class DocumentError(ValueError):
    pass


def folder():
    path = config.DATA_DIR / "documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_text(data, suffix):
    """Plain text from PDF or DOCX bytes."""
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        else:
            from docx import Document
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:                      # resumes often use tables for layout
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(parts)
    except Exception as e:  # damaged or password-protected files
        raise DocumentError(f"Couldn't read the text in that file ({e.__class__.__name__}). "
                            "You can paste the text in instead.")
    # Tidy up: drop blank lines and trailing spaces.
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line.strip())[:60000]


def save_upload(file_storage):
    """Check and store an uploaded file. Returns (original name, stored name, size, extracted text)."""
    original = Path(file_storage.filename or "").name
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED:
        raise DocumentError("Upload a PDF or a Word (.docx) file.")
    data = file_storage.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise DocumentError("That file is over 10 MB.")
    if not data.startswith(ALLOWED[suffix]):
        raise DocumentError(f"That doesn't look like a real {suffix} file.")
    text = extract_text(data, suffix)
    stored = f"{secrets.token_hex(12)}{suffix}"
    (folder() / stored).write_bytes(data)
    return original, stored, len(data), text


def path_of(stored_name):
    """Full path of a stored file, refusing anything that isn't a plain name in our folder."""
    if not stored_name or Path(stored_name).name != stored_name:
        return None
    path = folder() / stored_name
    return path if path.is_file() else None


def delete_file(stored_name):
    path = path_of(stored_name)
    if path:
        path.unlink()
