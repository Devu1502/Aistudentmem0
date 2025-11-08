from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ModelSettings:
    chat: str = "gpt-5-nano"
    summary: str = "llama3"
    embed: str = "nomic-embed-text:latest"

@dataclass(frozen=True)
class VectorSettings:
    chat_collection: str = "mem0_local"
    document_collection: str = "mem0_documents"
    embedding_dim: int = 768
    document_chunk_chars: int = 1200
    chat_search_limit: int = 5
    document_search_limit: int = 5

@dataclass(frozen=True)
class Settings:
    base_dir: Path = Path(__file__).resolve().parent.parent
    db_path: Path = base_dir / "chat_history_memori.db"
    models: ModelSettings = ModelSettings()
    vectors: VectorSettings = VectorSettings()
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # Qdrant Cloud configuration (env overrides baked-in defaults)
    qdrant_url: str = os.getenv(
        "QDRANT_URL",
        "https://75980000-12ff-49b5-8bee-f4e30ac3353a.us-east4-0.gcp.cloud.qdrant.io:6333",
    )
    qdrant_api_key: str = os.getenv(
        "QDRANT_API_KEY",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.ZbZSc4J8Y20_twaDVla2xCOqVigNfp7q7czfN-q2IVI",
    )

settings = Settings()
