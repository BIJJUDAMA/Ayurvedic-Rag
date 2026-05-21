import os

# --- Configuration ---
FILE_PATH = "books/astanga_hridaya/astanga-hridaya.md"
COLLECTION_NAME = "ayurveda_samhitas"
SOURCE_TREATISE = "astanga_hridaya"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333

# Use local model if available, otherwise download
LOCAL_MODEL_PATH = os.path.join("models", "nomic-embed-text-v2-moe")
EMBEDDING_MODEL = LOCAL_MODEL_PATH if os.path.exists(LOCAL_MODEL_PATH) else "nomic-ai/nomic-embed-text-v2-moe"

VECTOR_SIZE = 768
