from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import audio, chat, documents, memory as memory_router, search, sessions, system
import routers.search  # <--- force ensure route registration


app = FastAPI(title="Mem0 Local Memory System")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://f717d785d181.ngrok-free.app",  # 👈 add this line

    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(audio.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(sessions.router)
app.include_router(memory_router.router)


@app.get("/")
def root():
    return {"message": "Mem0 + Ollama + Qdrant fully local memory server running"}
