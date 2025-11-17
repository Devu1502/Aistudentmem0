from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from memory import LocalMemory
from services.dependencies import get_memory_store
from services.auth_service import protect


router = APIRouter()


@router.post("/add")
def add_memory(
    text: str = Query(..., description="Content to store"),
    topic: str = "general",
    session_id: str | None = None,
    memory_type: str = "short_term",
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    user_id = current_user["id"]
    session = session_id or "default"
    result = memory_store.add(
        text,
        user_id=user_id,
        agent_id=topic,
        run_id=session,
        metadata={"type": memory_type},
    )
    print("\n[DEBUG] Added memory:")
    print(result)
    return {"session_id": session, "added": result}


@router.get("/search")
def search_memory(
    query: str,
    topic: str | None = None,
    session_id: str | None = None,
    memory_type: str | None = None,
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    user_id = current_user["id"]
    filters = {}
    if memory_type:
        filters["type"] = memory_type

    results = memory_store.search(
        query=query,
        user_id=user_id,
        agent_id=topic,
        run_id=session_id,
        filters=filters,
    )
    return {"query": query, "results": results}


@router.get("/all")
def get_all(
    topic: str | None = None,
    session_id: str | None = None,
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    raw = memory_store.get_all(user_id=current_user["id"], agent_id=topic, run_id=session_id)
    results = raw.get("results") if isinstance(raw, dict) else raw
    if results is None:
        results = []
    print("\n[DEBUG] formatted results array:", results)
    return {"memories": results}


@router.post("/update")
def update_memory(
    memory_id: str,
    new_text: str,
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    result = memory_store.update(memory_id=memory_id, data=new_text)
    return {"updated": result}


@router.delete("/delete")
def delete_memory(
    memory_id: str | None = None,
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    if memory_id:
        memory_store.delete(memory_id=memory_id)
        return {"deleted_id": memory_id}
    memory_store.delete_all(user_id=current_user["id"])
    return {"deleted_all_for_user": current_user["id"]}


@router.post("/reset")
def reset_all(memory_store: LocalMemory = Depends(get_memory_store), current_user: dict = Depends(protect)):
    memory_store.reset()
    return {"message": "All memories reset"}


@router.get("/search_topic")
def search_topic(
    query: str = Query(..., description="Keyword to search"),
    limit: int = 5,
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    try:
        results = memory_store.search(query=query, user_id=current_user["id"])
    except Exception as search_err:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Vector search failed: {search_err}") from search_err

    hits = results.get("results", [])[:limit]
    formatted = [
        {
            "id": item.get("id"),
            "score": item.get("score"),
            "memory": item.get("memory"),
        }
        for item in hits
    ]
    return {"query": query, "results": formatted}


@router.get("/search_history")
def search_all(
    query: str = Query(...),
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    res = memory_store.search(query=query, user_id=current_user["id"])
    return {"query": query, "results": res}


@router.get("/inspect_memory")
def inspect_memory(memory_store: LocalMemory = Depends(get_memory_store), current_user: dict = Depends(protect)):
    short = memory_store.search(query="", user_id=current_user["id"], filters={"type": "short_term"})
    long = memory_store.search(query="", user_id=current_user["id"], filters={"type": "long_term"})
    print("\nShort-term records:")
    for i, s in enumerate(short.get("results", [])):
        print(f"{i+1}. {s.get('memory')[:100]}")

    print("\nLong-term records:")
    for i, l in enumerate(long.get("results", [])):
        print(f"{i+1}. {l.get('memory')[:100]}")

    return {"short_term": short, "long_term": long}
