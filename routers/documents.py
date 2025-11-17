from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException

from services.auth_service import protect

from services.dependencies import get_document_service
from services.document_service import DocumentIngestionService


router = APIRouter()


@router.post("/documents/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    document_service: DocumentIngestionService = Depends(get_document_service),
    current_user: dict = Depends(protect),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Upload up to five files at a time.")

    uploaded, errors = await document_service.ingest(files, current_user["id"])
    if not uploaded and errors:
        raise HTTPException(status_code=500, detail={"errors": errors})

    return {"uploaded": uploaded, "errors": errors}
