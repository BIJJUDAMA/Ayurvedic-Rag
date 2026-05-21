from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
from .config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, EMBEDDING_MODEL, VECTOR_SIZE, SOURCE_TREATISE

def upload_to_qdrant(chunks: List[Dict[str, Any]], model: SentenceTransformer = None):
    if model is None:
        print(f"Initializing embedding model: {EMBEDDING_MODEL}...")
        model = SentenceTransformer(EMBEDDING_MODEL, trust_remote_code=True)
    else:
        print("Using shared embedding model instance...")
        
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Check if collection exists, if not create it
    if not client.collection_exists(COLLECTION_NAME):
        print(f"Creating unified collection '{COLLECTION_NAME}'...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
        )

    points = []
    print(f"Generating embeddings and preparing points for {len(chunks)} chunks...")
    for i, chunk in enumerate(chunks):
        if (i + 1) % 100 == 0:
            print(f" Embedded {i + 1}/{len(chunks)}...")
        
        embedding = model.encode(chunk["content"]).tolist()
        
        payload = {
            "source_treatise": SOURCE_TREATISE,
            "canonical_id": chunk.get("canonical_id", "root"),
            "parent_id": chunk.get("parent_id"),
            "prev_id": chunk.get("prev_id"),
            "next_id": chunk.get("next_id"),
            "level": chunk["level"],
            "title": chunk["title"],
            "content": chunk["content"],
            "url": chunk.get("url", ""),
            **chunk.get("metadata", {})
        }
        
        points.append(models.PointStruct(
            id=chunk["id"],
            vector=embedding,
            payload=payload
        ))

    # Batch upload
    batch_size = 100
    print(f"Uploading to Qdrant in batches of {batch_size}...")
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )
        print(f"Uploaded batch {i // batch_size + 1}/{(len(points) - 1) // batch_size + 1}")
    
    print("Upload complete!")
