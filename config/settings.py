from __future__ import annotations

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
    ollama_url: str = "http://localhost:11434"
    qdrant_url: str = "http://localhost:6333"


settings = Settings()
