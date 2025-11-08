from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import List, Tuple

from fastapi import UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from doc_store import DocumentStore


class DocumentIngestionService:
    def __init__(self, document_store: DocumentStore) -> None:
        self.document_store = document_store

    async def ingest(self, files: List[UploadFile]) -> Tuple[List[dict], List[dict]]:
        uploaded: List[dict] = []
        errors: List[dict] = []

        for file in files:
            suffix = os.path.splitext(file.filename or "document")[1] or ".bin"
            try:
                contents = await file.read()
                if not contents:
                    raise ValueError("Empty file.")

                text_content = self._extract_text(contents, suffix)
                metadata = {
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "uploaded_at": datetime.utcnow().isoformat(),
                }
                store_result = self.document_store.add_document(
                    file.filename or "Untitled",
                    text_content,
                    metadata=metadata,
                )
                uploaded.append(
                    {
                        "filename": file.filename,
                        "doc_id": store_result["doc_id"],
                        "chunks": store_result["chunks"],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"filename": file.filename, "error": str(exc)})

        return uploaded, errors

    def _extract_text(self, raw_bytes: bytes, suffix: str) -> str:
        ext = suffix.lower()
        if ext == ".pdf":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            try:
                reader = PdfReader(tmp_path)
                pages: List[str] = []
                for page in reader.pages:
                    try:
                        page_text = page.extract_text() or ""
                    except Exception:
                        page_text = ""
                    if page_text:
                        pages.append(page_text)
                text = "\n".join(pages).strip()
                if not text:
                    raise ValueError("No text extracted from PDF.")
                return text
            except PdfReadError as err:
                raise ValueError(f"Failed to read PDF: {err}") from err
            finally:
                os.remove(tmp_path)

        if ext in {".txt", ".md"}:
            text = raw_bytes.decode("utf-8", errors="ignore").strip()
            if not text:
                raise ValueError("No text extracted from document.")
            return text

        raise ValueError(f"Unsupported file type: {ext}")
