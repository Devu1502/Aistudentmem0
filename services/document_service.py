from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import List, Tuple

from fastapi import UploadFile
from markitdown import MarkItDown

from doc_store import DocumentStore


class DocumentIngestionService:
    def __init__(self, document_store: DocumentStore) -> None:
        self.document_store = document_store
        self.markdown_converter = MarkItDown(enable_plugins=False)

    async def ingest(self, files: List[UploadFile]) -> Tuple[List[dict], List[dict]]:
        uploaded: List[dict] = []
        errors: List[dict] = []

        for file in files:
            suffix = os.path.splitext(file.filename or "document")[1] or ".bin"
            try:
                contents = await file.read()
                if not contents:
                    raise ValueError("Empty file.")

                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(contents)
                    tmp_path = tmp.name

                try:
                    result = self.markdown_converter.convert(tmp_path)
                    text_content = (result.text_content or "").strip()
                    if not text_content:
                        raise ValueError("No text extracted from document.")

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
                finally:
                    os.remove(tmp_path)
            except Exception as exc:  # noqa: BLE001
                errors.append({"filename": file.filename, "error": str(exc)})

        return uploaded, errors
