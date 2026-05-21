# --- Configuration for Charaka Samhita ---
import os

BOOKS_DIR = "books/charak_samhita"
COLLECTION_NAME = "ayurveda_samhitas"
SOURCE_TREATISE = "charak_samhita"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333

# Use local model if available, otherwise download
LOCAL_MODEL_PATH = os.path.join("models", "nomic-embed-text-v2-moe")
EMBEDDING_MODEL = LOCAL_MODEL_PATH if os.path.exists(LOCAL_MODEL_PATH) else "nomic-ai/nomic-embed-text-v2-moe"

VECTOR_SIZE = 768

# Document Types
TYPE_BOTANICAL = "stub_botanical"
TYPE_GLOSSARY = "stub_glossary"
TYPE_CONCEPT = "concept_article"
TYPE_PROCEDURAL = "procedural_article"
TYPE_STHANA = "sthana_index"
TYPE_CHAPTER = "chapter_root"
TYPE_SECTION = "section"
TYPE_VERSE = "verse_block"
TYPE_APPARATUS = "apparatus"
