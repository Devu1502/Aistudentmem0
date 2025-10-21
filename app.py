from fastapi import FastAPI
from mem0 import Memory

app = FastAPI()

config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "test",
            "host": "localhost",
            "port": 6333,
            "embedding_model_dims": 768,
        },
    },
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3:latest",  # You can use gpt-oss:latest too
            "temperature": 0,
            "max_tokens": 1000,
            "ollama_base_url": "http://localhost:11434",
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text:latest",
            "ollama_base_url": "http://localhost:11434",
        },
    },
}

m = Memory.from_config(config)

@app.get("/")
def home():
    return {"message": "Mem0 + Ollama + Qdrant running locally"}

@app.post("/add")
def add_memory():
    result = m.add("I love working with local AI models.", user_id="sree")
    return {"added": result}

@app.get("/all")
def get_all():
    memories = m.get_all(user_id="sree")
    return {"memories": memories}
