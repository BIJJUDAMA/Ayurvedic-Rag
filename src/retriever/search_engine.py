import re
import numpy as np
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from qdrant_client import QdrantClient
from qdrant_client.http import models
from src.chunking.remote_embedder import RemoteEmbedder
from indic_transliteration import sanscript
from indic_transliteration.sanscript import SCHEMES, transliterate

# Setup logging
logger = logging.getLogger("AyurvedaSearchEngine")

class AyurvedaSearchEngine:
    def __init__(self, 
                 client: QdrantClient,
                 collection_name: str = "ayurveda_rag", 
                 model: RemoteEmbedder = None):
        
        self.client = client
        self.collection_name = collection_name
        # Expecting RemoteEmbedder here
        self.model = model or RemoteEmbedder()

    def _normalize_query(self, query: str) -> str:
        """Expand query with Devanagari/IAST only if Sanskrit is detected."""
        try:
            # Detect Sanskrit (Devanagari or common IAST chars)
            has_dev = bool(re.search(r'[\u0900-\u097F]', query))
            has_iast = bool(re.search(r'[āīūṛṝḷḹṅñṭḍṇśṣḥṃ]', query, re.IGNORECASE))
            
            if has_dev:
                iast = transliterate(query, sanscript.DEVANAGARI, SCHEMES[sanscript.IAST])
                return f"{query} {iast}"
            elif has_iast:
                dev = transliterate(query, sanscript.IAST, SCHEMES[sanscript.DEVANAGARI])
                return f"{query} {dev}"
            else:
                # English only: don't transliterate, just return query
                return query
        except:
            return query

    def hybrid_search(self, 
                      text_query: str, 
                      expanded_queries: Optional[List[str]] = None,
                      top_k: int = 5, 
                      treatise_filter: Optional[str] = None,
                      intent_filter: Optional[str] = None,
                      citation_params: Optional[Dict[str, Any]] = None,
                      original_user_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Ayurveda RAG 2026: Multi-Query Double-E5 + SPLADE Native Hybrid Search.
        Fuses results from multiple query variations and implements citation-aware metadata filtering.
        """
        logger.info(f"Executing High-Recall Hybrid Retrieval for: {text_query}")
        
        # 1. Prepare Search Variations
        search_variations = [text_query]
        
        if original_user_query and original_user_query != text_query:
            search_variations.append(original_user_query)
            
        sanskrit_term = None
        if expanded_queries:
            sanskrit_term = expanded_queries[0]
            search_variations.append(sanskrit_term)
            
        if intent_filter and intent_filter != "Sloka":
            search_variations.append(f"{text_query} {intent_filter}")
        if treatise_filter:
            search_variations.append(f"{text_query} {treatise_filter}")

        # Remove duplicates
        search_variations = list(dict.fromkeys(search_variations))

        # 2. Build Filter
        must_conditions = []
        
        if citation_params:
            if citation_params.get("treatise"):
                must_conditions.append(models.FieldCondition(key="source_treatise", match=models.MatchValue(value=citation_params["treatise"])))
            if citation_params.get("chapter"):
                must_conditions.append(models.FieldCondition(key="chapter_number", match=models.MatchValue(value=citation_params["chapter"])))
            if citation_params.get("verse"):
                v = citation_params["verse"]
                must_conditions.append(models.FieldCondition(key="verse_ref", match=models.MatchValue(value=str(v))))

        query_filter = models.Filter(must=must_conditions) if must_conditions else None

        # 3. Parallel Prefetch & Fusion
        query_prefix = "query: "
        prefetch_queries = []
        
        for q in search_variations:
            norm_q = self._normalize_query(q)
            # Dense English
            v_eng = self.model.encode(f"{query_prefix}{q}").tolist()
            # Dense Sanskrit (Cross-lingual)
            v_san = self.model.encode(f"{query_prefix}{norm_q}").tolist()
            # Sparse SPLADE
            sparse_dict = self.model.encode_sparse(norm_q)
            v_sparse = models.SparseVector(indices=[int(k) for k in sparse_dict.keys()], values=[float(v) for v in sparse_dict.values()])
            
            # Weighted Prefetch
            prefetch_queries.append(models.Prefetch(query=v_eng, using="dense_english", limit=100, filter=query_filter))
            prefetch_queries.append(models.Prefetch(query=v_san, using="dense_sanskrit", limit=30, filter=query_filter))
            prefetch_queries.append(models.Prefetch(query=v_sparse, using="sparse_splade", limit=50, filter=query_filter))

        try:
            # Increased limit to 400 for maximum candidate coverage during reranking
            search_result = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch_queries,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=400
            )
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

        print(f"DEBUG: Qdrant returned {len(search_result.points)} points")
        if not search_result.points: return []

        # 4. Expert Reranking
        candidate_points = search_result.points
        candidate_texts = [f"[Source: {p.payload.get('source_treatise')}] Content: {p.payload.get('content')}" for p in candidate_points]
        
        # Cleanest, most comprehensive query is the best for reranking
        rerank_query = original_user_query if original_user_query else text_query
        if sanskrit_term:
            rerank_query = f"{rerank_query} {sanskrit_term}"
            
        rerank_scores = self.model.rerank(rerank_query, candidate_texts)
        
        final_results = []
        for i, point in enumerate(candidate_points):
            raw_score = float(rerank_scores[i])
            boosted_score = np.exp(raw_score * 3.0) 

            final_results.append({
                "id": point.id,
                "score": boosted_score,
                "title": point.payload.get("section_title") or point.payload.get("chapter_title") or point.payload.get("content", "")[:80],
                "text": point.payload.get("content", ""),
                "source": point.payload.get("source_treatise", ""),
                "metadata": point.payload
            })
        
        return sorted(final_results, key=lambda x: x["score"], reverse=True)[:top_k]

    def search(self, 
               original_query: str, 
               expanded_queries: List[str] = None, 
               top_n: int = 5, 
               intent_filter: Optional[str] = None, 
               treatise_filter: Optional[str] = None,
               citation_params: Optional[Dict[str, Any]] = None,
               original_user_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Unified search method used by the agent and evaluation scripts."""
        return self.hybrid_search(
            text_query=original_query, 
            expanded_queries=expanded_queries,
            top_k=top_n, 
            treatise_filter=treatise_filter, 
            intent_filter=intent_filter,
            citation_params=citation_params,
            original_user_query=original_user_query
        )
