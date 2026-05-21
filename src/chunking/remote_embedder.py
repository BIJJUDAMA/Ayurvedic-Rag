import requests
import numpy as np
from typing import List, Dict

class RemoteEmbedder:
    """Client for the sidecar GPU inference service."""
    def __init__(self, url="http://localhost:8080"):
        self.url = url
        self.health_url = f"{url}/health"
        self.embed_url = f"{url}/embed"
        self.sparse_url = f"{url}/sparse-embed"
        self.rerank_url = f"{url}/rerank"

    def is_available(self):
        try:
            response = requests.get(self.health_url, timeout=2)
            return response.status_code == 200
        except:
            return False

    def encode(self, sentences, **kwargs):
        # Determine if we should return a single vector or a list of vectors
        is_single = isinstance(sentences, str)
        if is_single:
            sentences = [sentences]
            
        response = requests.post(
            self.embed_url,
            json={"sentences": sentences},
            timeout=120
        )
        response.raise_for_status()
        
        embeddings = np.array(response.json()["embeddings"])
        return embeddings[0] if is_single else embeddings

    def encode_sparse(self, sentences: List[str]) -> List[Dict[int, float]]:
        """Get sparse SPLADE embeddings from the GPU service."""
        is_single = isinstance(sentences, str)
        if is_single:
            sentences = [sentences]
            
        response = requests.post(
            self.sparse_url, 
            json={"sentences": sentences},
            timeout=120
        )
        response.raise_for_status()
        
        results = response.json()["sparse_embeddings"]
        return results[0] if is_single else results

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        """Send reranking request to the GPU Sidecar."""
        if not documents:
            return []
            
        response = requests.post(
            self.rerank_url,
            json={"query": query, "documents": documents},
            timeout=120
        )
        response.raise_for_status()
        return response.json()["scores"]
