from functools import lru_cache

from qdrant_client import QdrantClient

from config.settings import settings
from doc_store import DocumentStore
from memory import LocalMemory, OpenAIEmbedder
from services.chat_service import ChatService
from services.document_service import DocumentIngestionService


@lru_cache
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        prefer_grpc=False,
        timeout=10.0,
    )


@lru_cache
def get_embedder() -> OpenAIEmbedder:
    return OpenAIEmbedder(model=settings.models.embed)


@lru_cache
def get_memory_store() -> LocalMemory:
    return LocalMemory(
        qdrant_client=get_qdrant_client(),
        embedder=get_embedder(),
        collection_name=settings.vectors.chat_collection,
        dimension=settings.vectors.embedding_dim,
    )


@lru_cache
def get_document_store() -> DocumentStore:
    return DocumentStore(
        qdrant_client=get_qdrant_client(),
        embedder=get_embedder(),
        collection_name=settings.vectors.document_collection,
        dimension=settings.vectors.embedding_dim,
    )


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(memory_store=get_memory_store(), document_store=get_document_store())


@lru_cache
def get_document_service() -> DocumentIngestionService:
    return DocumentIngestionService(document_store=get_document_store())
