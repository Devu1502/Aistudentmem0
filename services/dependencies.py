# Provide cached dependency factories for the FastAPI app.
from functools import lru_cache

from qdrant_client import QdrantClient

from config.settings import settings
from doc_store import DocumentStore
from memory import LocalMemory, OpenAIEmbedder
from services.chat_service import ChatService
from services.document_service import DocumentIngestionService


# Reuse a single Qdrant client to avoid reconnect cost.
@lru_cache
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        prefer_grpc=False,
        timeout=10.0,
    )


# Share one embedder instance configured with the preferred model.
@lru_cache
def get_embedder() -> OpenAIEmbedder:
    return OpenAIEmbedder(model=settings.models.embed)


# Wrap the chat memory store with cached configuration.
@lru_cache
def get_memory_store() -> LocalMemory:
    return LocalMemory(
        qdrant_client=get_qdrant_client(),
        embedder=get_embedder(),
        collection_name=settings.vectors.chat_collection,
        dimension=settings.vectors.embedding_dim,
    )


# Provide a cached document store for ingestion and retrieval.
@lru_cache
def get_document_store() -> DocumentStore:
    return DocumentStore(
        qdrant_client=get_qdrant_client(),
        embedder=get_embedder(),
        collection_name=settings.vectors.document_collection,
        dimension=settings.vectors.embedding_dim,
    )


# Wire up the chat service once so routes can pull it in quickly.
@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(memory_store=get_memory_store(), document_store=get_document_store())


# Same idea for the document ingestion service.
@lru_cache
def get_document_service() -> DocumentIngestionService:
    return DocumentIngestionService(document_store=get_document_store())
