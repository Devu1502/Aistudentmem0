from __future__ import annotations

from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Query

from doc_store import DocumentStore
from memory import LocalMemory
from services.dependencies import get_document_store, get_memory_store
from services.auth_service import protect


router = APIRouter()


def _annotate_results(results: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for item in results:
        annotated.append(
            {
                **item,
                "source": source,
                "score": item.get("score"),
            }
        )
    return annotated


def _score_value(item: Dict[str, Any]) -> float:
    score = item.get("score")
    return float(score) if isinstance(score, (int, float)) else float("-inf")


@router.get("/vectorsearch")
def vector_search(
    query: str = Query(..., description="Text to search across chat memories and documents."),
    limit: int = Query(5, ge=1, le=50, description="Maximum number of results to retrieve from each source."),
    memory_store: LocalMemory = Depends(get_memory_store),
    document_store: DocumentStore = Depends(get_document_store),
    current_user: dict = Depends(protect),
):
    user_id = current_user["id"]
    chat_hits = memory_store.search(query=query, user_id=user_id, limit=limit).get("results", [])
    doc_hits = document_store.search(query=query, limit=limit, filters={"user_id": user_id}).get("results", [])

    annotated_chat = _annotate_results(chat_hits, "memory")
    annotated_docs = _annotate_results(doc_hits, "document")
    combined = sorted(annotated_chat + annotated_docs, key=_score_value, reverse=True)

    return {
        "query": query,
        "chat_results": annotated_chat,
        "document_results": annotated_docs,
        "combined_results": combined,
    }


@router.get("/documentvectorsearch")
def document_vector_search(
    query: str = Query(..., description="Text to search within uploaded documents."),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of document matches to return."),
    document_store: DocumentStore = Depends(get_document_store),
    current_user: dict = Depends(protect),
):
    doc_hits = document_store.search(query=query, limit=limit, filters={"user_id": current_user["id"]}).get("results", [])
    annotated_docs = _annotate_results(doc_hits, "document")
    return {"query": query, "results": annotated_docs}
