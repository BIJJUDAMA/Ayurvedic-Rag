from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
from .config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, EMBEDDING_MODEL, VECTOR_SIZE, SOURCE

def upload_to_qdrant(chunks: List[Dict[str, Any]], model: SentenceTransformer = None):
    if model is None:
        print(f"Initializing embedding model: {EMBEDDING_MODEL}...")
        # Nomic V2 requires trust_remote_code=True
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
        if (i + 1) % 50 == 0:
            print(f" Embedded {i + 1}/{len(chunks)}...")
        embedding = model.encode(chunk["content"]).tolist()
        
        # Merge metadata into payload
        payload = {
            "source": SOURCE,
            "level": chunk["level"],
            "parent_id": chunk.get("parent_id"),
            "prev_id": chunk.get("prev_id"),
            "next_id": chunk.get("next_id"),
            "content": chunk["content"],
            **chunk.get("metadata", {})
        }
        
        # Ensure all UUIDs are strings
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
