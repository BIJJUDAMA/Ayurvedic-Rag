import requests
import numpy as np
from typing import List, Dict
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class RemoteEmbedder:
    """Client for the sidecar GPU inference service with automatic retries."""
    def __init__(self, url="http://localhost:8080"):
        self.url = url
        self.health_url = f"{url}/health"
        self.embed_url = f"{url}/embed"
        self.sparse_url = f"{url}/sparse-embed"
        self.rerank_url = f"{url}/rerank"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=False
    )
    def is_available(self):
        try:
            response = requests.get(self.health_url, timeout=5)
            return response.status_code == 200
        except:
            return False

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.HTTPError)),
        reraise=True
    )
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

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.HTTPError)),
        reraise=True
    )
    def encode_sparse(self, sentences: List[str]) -> List[Dict[int, float]]:
        """Get sparse SPLADE embeddings from the GPU service with retries."""
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

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.HTTPError)),
        reraise=True
    )
    def rerank(self, query: str, documents: List[str]) -> List[float]:
        """Send reranking request to the GPU Sidecar with retries."""
        if not documents:
            return []
            
        response = requests.post(
            self.rerank_url,
            json={"query": query, "documents": documents},
            timeout=120
        )
        response.raise_for_status()
        return response.json()["scores"]
