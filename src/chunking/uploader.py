import os
import json
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from src.chunking.remote_embedder import RemoteEmbedder
from tqdm import tqdm

class AyurvedaUploader:
    """
    Unified uploader for pushing processed Ayurveda chunks to Qdrant.
    Supports multi-vector (dense + sparse) indexing.
    """
    def __init__(self, qdrant_host: str = "localhost", qdrant_port: int = 6333, embedder_url: str = "http://localhost:8080"):
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.embedder = RemoteEmbedder(url=embedder_url)
        self.collection_name = "ayurveda_rag"
        self._collection_ready = False

    def setup_collection(self):
        """Ensures the collection exists with the correct multi-vector config."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                print(f"Creating collection '{self.collection_name}'...")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "dense_english": models.VectorParams(
                            size=1024, 
                            distance=models.Distance.COSINE,
                            on_disk=True # Enable Memory Mapping for RAM efficiency
                        ),
                        "dense_sanskrit": models.VectorParams(
                            size=1024, 
                            distance=models.Distance.COSINE,
                            on_disk=True
                        ),
                    },
                    sparse_vectors_config={
                        "sparse_splade": models.SparseVectorParams(
                            index=models.SparseIndexParams(
                                on_disk=True
                            )
                        )
                    }
                )
                print(f" [OK] Collection '{self.collection_name}' created with On-Disk Memmap enabled.")
            else:
                print(f"Collection '{self.collection_name}' already exists.")
            
            self._collection_ready = True
        except Exception as e:
            print(f" [!] Error setting up collection: {e}")
            raise

    def upload_book(self, book_dir_name: str, batch_size: int = 32):
        """
        Reads vectors.jsonl for a given book and uploads to Qdrant in batches.
        """
        if not self._collection_ready:
            self.setup_collection()

        jsonl_path = os.path.join("processed-books", book_dir_name, "vectors.jsonl")
        if not os.path.exists(jsonl_path):
            print(f" [!] Error: {jsonl_path} not found. Run the chunking pipeline first.")
            return

        # Load chunks from JSONL
        print(f"Reading chunks from {jsonl_path}...")
        chunks = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    chunks.append(json.loads(line))

        if not chunks:
            print(f" [!] Warning: No chunks found in {jsonl_path}")
            return

        print(f"Uploading {len(chunks)} chunks from '{book_dir_name}' to Qdrant (batch_size={batch_size})...")
        
        # Process in batches
        for i in tqdm(range(0, len(chunks), batch_size)):
            batch = chunks[i:i + batch_size]
            try:
                self._upload_batch(batch, book_dir_name)
            except Exception as e:
                print(f" [!] Error uploading batch at index {i}: {e}")
                continue

        print(f"✔ Finished uploading '{book_dir_name}'.")

    def _upload_batch(self, batch: List[Dict[str, Any]], book_dir_name: str):
        """Processes and uploads a single batch of points."""
        
        # 1. Prepare texts for embedding
        contents = [f"passage: {chunk['content']}" for chunk in batch]
        
        # 2. Generate embeddings
        dense_vecs = self.embedder.encode(contents)
        sparse_vecs = self.embedder.encode_sparse(contents)
        
        points = []
        for j, chunk in enumerate(batch):
            point_id = chunk["id"]
            
            # Prepare payload - flattened for better filtering
            # We enforce source = book_dir_name to ensure consistency across the collection
            payload = {
                "title": chunk.get("title"),
                "content": chunk.get("content"),
                "level": chunk.get("level"),
                "parent_id": chunk.get("parent_id"),
                "prev_id": chunk.get("prev_id"),
                "next_id": chunk.get("next_id"),
                "url": chunk.get("url"),
                "metadata": chunk.get("metadata", {}),
                "source": book_dir_name
            }
            
            # Vector mapping
            # dense_english and dense_sanskrit share the same multilingual embedding
            # in this unified schema.
            vectors = {
                "dense_english": dense_vecs[j].tolist(),
                "dense_sanskrit": dense_vecs[j].tolist(),
                "sparse_splade": models.SparseVector(
                    indices=list(map(int, sparse_vecs[j].keys())),
                    values=list(map(float, sparse_vecs[j].values()))
                )
            }
            
            points.append(models.PointStruct(
                id=point_id,
                vector=vectors,
                payload=payload
            ))
            
        # 3. Upsert to Qdrant
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True
        )

if __name__ == "__main__":
    import sys
    
    uploader = AyurvedaUploader()
    
    # If book names are provided as CLI args, process them
    if len(sys.argv) > 1:
        for book in sys.argv[1:]:
            uploader.upload_book(book)
    else:
        print("Usage: python src/chunking/uploader.py <book_dir1> <book_dir2> ...")
        print("Example: python src/chunking/uploader.py charak_samhita shusrut_samhita astanga_hridaya")
