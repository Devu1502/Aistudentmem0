from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

from config.settings import settings
from routers import audio, auth, chat, documents, memory as memory_router, search, sessions, system
import routers.search  # <--- force ensure route registration


app = FastAPI(title="Mem0 Local Memory System")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_db_client():
    mongo_client = MongoClient(settings.mongodb_uri)
    mongo_db = mongo_client["AIBuddy"]
    app.state.mongo_client = mongo_client
    app.state.mongo_db = mongo_db
    app.state.users = mongo_db["users"]
    app.state.password_reset_tokens = mongo_db["password_reset_tokens"]
    app.state.users.create_index("email", unique=True)
    reset_col = app.state.password_reset_tokens
    reset_col.create_index("token", unique=True)
    reset_col.create_index("expires_at", expireAfterSeconds=0)


@app.on_event("shutdown")
def shutdown_db_client():
    client = getattr(app.state, "mongo_client", None)
    if client:
        client.close()


app.include_router(system.router)
app.include_router(audio.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(sessions.router)
app.include_router(memory_router.router)
app.include_router(auth.router)


@app.get("/")
def root():
    return {"message": "Mem0 + Ollama + Qdrant fully local memory server running"}
