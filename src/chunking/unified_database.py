import os
import re
import sys
from typing import List, Dict, Any, Optional

# Configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "ayurveda_rag"
VECTOR_SIZE = 1024 # Multilingual-E5-Large dimension

class AyurvedaDatabaseManager:
    def __init__(self, dense_model: Optional[Any] = None):
        from qdrant_client import QdrantClient
        from qdrant_client.http import models
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.models = models
        
        if dense_model:
            self.dense_model = dense_model
        else:
            from src.chunking.remote_embedder import RemoteEmbedder
            self.dense_model = RemoteEmbedder()
        
        # Ensure collection exists with Named Vectors
        if self.client.collection_exists(COLLECTION_NAME):
            # Schema Validation: Check if the vector names match our new architecture
            collection_info = self.client.get_collection(COLLECTION_NAME)
            existing_vectors = collection_info.config.params.vectors
            
            # If we find the old 'dense_iast' name or mismatched schema, we must recreate
            if "dense_sanskrit" not in existing_vectors:
                print(f"⚠ Schema Mismatch detected in '{COLLECTION_NAME}'. Recreating for Double-E5 upgrade...")
                self.client.delete_collection(COLLECTION_NAME)
            else:
                print(f"✔ Collection '{COLLECTION_NAME}' matches the Double-E5 schema.")

        if not self.client.collection_exists(COLLECTION_NAME):
            print(f"Initializing collection '{COLLECTION_NAME}' with 1024-dim Named Vectors...")
            
            vectors_config = {
                "dense_english": models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE
                ),
                "dense_sanskrit": models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE
                )
            }
            
            sparse_vectors_config = {
                "sparse_splade": models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False)
                )
            }
            
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_vectors_config,
            )
            print(f"✔ Collection '{COLLECTION_NAME}' created.")

    def _normalize_sanskrit(self, text: str) -> str:
        """Provide balanced context for Multilingual-E5 by combining Devanagari and IAST."""
        try:
            from indic_transliteration import sanscript
            from indic_transliteration.sanscript import SCHEMES, transliterate
            
            # Detect script
            has_dev = bool(re.search(r'[\u0900-\u097F]', text))
            if has_dev:
                iast = transliterate(text, sanscript.DEVANAGARI, SCHEMES[sanscript.IAST])
                # Return both to give the multilingual model more 'clues'
                return f"{text} {iast}"
            else:
                dev = transliterate(text, sanscript.IAST, SCHEMES[sanscript.DEVANAGARI])
                return f"{text} {dev}"
        except Exception as e:
            return text

    def upload_chunks(self, chunks: List[Dict[str, Any]], source: str):
        from qdrant_client.http import models
        print(f"Preparing Ayurveda 2026 Double-E5 + SPLADE payload for {len(chunks)} chunks from {source}...")
        
        points = []
        for i, chunk in enumerate(chunks):
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(chunks)}...")

            content = chunk["content"]
            title = chunk.get("section_title") or chunk.get("chapter_title") or chunk.get("title", "")
            
            # E5 Prefix requirement: "passage: " for indexing
            indexing_prefix = "passage: "
            
            # 1. Generate Dense Vectors
            # Vector 1: English Semantic (Using English translation)
            dense_english = self.dense_model.encode(f"{indexing_prefix}{title} {content}").tolist()
            
            # Vector 2: Sanskrit Semantic (Using Devanagari + IAST)
            sanskrit_context = self._normalize_sanskrit(f"{title} {content}")
            dense_sanskrit = self.dense_model.encode(f"{indexing_prefix}{sanskrit_context}").tolist()

            # 2. Generate Sparse Vector (SPLADE) via GPU Sidecar
            sparse_dict = self.dense_model.encode_sparse(f"{title} {content}")
            sparse_vec = models.SparseVector(
                indices=[int(k) for k in sparse_dict.keys()],
                values=[float(v) for v in sparse_dict.values()]
            )

            # 3. Build Multi-Vector Object
            vectors = {
                "dense_english": dense_english,
                "dense_sanskrit": dense_sanskrit,
                "sparse_splade": sparse_vec
            }

            # 4. Payload
            payload = {
                "source": source,
                "level": chunk["level"],
                "content": content,
                "parent_id": chunk.get("parent_id"),
                "prev_id": chunk.get("prev_id"),
                "next_id": chunk.get("next_id"),
                **chunk.get("metadata", {})
            }

            points.append(models.PointStruct(
                id=chunk["id"],
                vector=vectors,
                payload=payload
            ))

        # Batch Upload
        batch_size = 50
        print(f"Upserting {len(points)} points to '{COLLECTION_NAME}'...")
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=batch
            )
        
        print(f"✔ Successfully uploaded {len(chunks)} chunks from {source}.")

if __name__ == "__main__":
    import json
    
    manager = AyurvedaDatabaseManager()
    
    books = ["charak_samhita", "shusrut_samhita", "astanga_hridaya"]
    
    for book in books:
        jsonl_path = os.path.join("processed-books", book, "vectors.jsonl")
        if not os.path.exists(jsonl_path):
            print(f"Skipping {book}: {jsonl_path} not found.")
            continue
            
        print(f"Loading chunks for {book}...")
        chunks = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    chunks.append(json.loads(line))
        
        if chunks:
            manager.upload_chunks(chunks, book)

def upload_to_qdrant(chunks: List[Dict[str, Any]], source: str, model: Any = None):
    manager = AyurvedaDatabaseManager(dense_model=model)
    manager.upload_chunks(chunks, source)
