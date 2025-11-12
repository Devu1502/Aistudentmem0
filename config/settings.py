from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ModelSettings:
    """Model configuration for chat, summarization, and embedding."""
    chat: str = "gpt-5-nano"
    summary: str = "gpt-5-nano"
    embed: str = "text-embedding-3-small"


@dataclass(frozen=True)
class VectorSettings:
    """Vector configuration for Qdrant collections and limits."""
    chat_collection: str = "mem0_local"
    document_collection: str = "mem0_documents"
    embedding_dim: int = 768
    document_chunk_chars: int = 1200
    chat_search_limit: int = 5
    document_search_limit: int = 5


@dataclass(frozen=True)
class Settings:
    """Global configuration for local development."""
    base_dir: Path = Path(__file__).resolve().parent.parent
    db_path: Path = base_dir / "chat_history_memori.db.bak"  # disabled local SQLite

    models: ModelSettings = ModelSettings()
    vectors: VectorSettings = VectorSettings()

    # MongoDB connection (Atlas + local fallback)
    mongodb_uri: str = os.getenv(
        "MONGODB_URI",
        "mongodb+srv://devananda1502_db_user:PDuFX3jYjvQJSLy3@aibuddy.furcexz.mongodb.net/?appName=AIBuddy",
    )

    # Frontend origin (defaults to local dev server)
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Qdrant connection
    qdrant_url: str = os.getenv(
        "QDRANT_URL",
        "https://75980000-12ff-49b5-8bee-f4e30ac3353a.us-east4-0.gcp.cloud.qdrant.io:6333",
    )
    qdrant_api_key: str = os.getenv(
        "QDRANT_API_KEY",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.ZbZSc4J8Y20_twaDVla2xCOqVigNfp7q7czfN-q2IVI",
    )

    environment: str = os.getenv("APP_ENV", "local")


# global settings
settings = Settings()
