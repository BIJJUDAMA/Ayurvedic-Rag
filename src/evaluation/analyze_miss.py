import os
import sys
import json
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.chunking.remote_embedder import RemoteEmbedder

def analyze_miss():
    client = QdrantClient(host='localhost', port=6333)
    model = RemoteEmbedder()
    
    # Query 3
    query = "What are the clinical signs and diagnostic features of a displaced bone fracture according to Sushruta Samhita?"
    expected_id = "1143aea2-f8d6-5466-88bc-0e9ea3f9aefb"
    
    for prefix in ["query: ", ""]:
        v_eng = model.encode(f"{prefix}{query}").tolist()
        sparse_dict = model.encode_sparse(query)
        v_sparse = models.SparseVector(indices=[int(k) for k in sparse_dict.keys()], values=[float(v) for v in sparse_dict.values()])
        
        # 1. Search in dense_english
        res_eng = client.query_points(
            collection_name="ayurveda_rag",
            prefetch=[
                models.Prefetch(query=v_eng, using="dense_english", limit=200)
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=200
        )
        rank_eng = -1
        for i, hit in enumerate(res_eng.points):
            if hit.id == expected_id:
                rank_eng = i + 1
                break
                
        # 2. Search in sparse_splade
        res_sparse = client.query_points(
            collection_name="ayurveda_rag",
            prefetch=[
                models.Prefetch(query=v_sparse, using="sparse_splade", limit=200)
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=200
        )
        rank_sparse = -1
        for i, hit in enumerate(res_sparse.points):
            if hit.id == expected_id:
                rank_sparse = i + 1
                break
                
        # 3. Rerank top 200 from Fusion
        # Simulate hybrid search logic
        fusion_res = client.query_points(
            collection_name="ayurveda_rag",
            prefetch=[
                models.Prefetch(query=v_eng, using="dense_english", limit=200),
                models.Prefetch(query=v_sparse, using="sparse_splade", limit=200)
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=200
        )
        
        candidate_texts = [f"[Source: {p.payload.get('source_treatise')}] Content: {p.payload.get('content')}" for p in fusion_res.points]
        rerank_scores = model.rerank(query, candidate_texts)
        
        # Zip and sort
        reranked = sorted(zip(fusion_res.points, rerank_scores), key=lambda x: x[1], reverse=True)
        
        rank_rerank = -1
        for i, (point, score) in enumerate(reranked):
            if point.id == expected_id:
                rank_rerank = i + 1
                break
                
        print(f"\n--- Prefix: '{prefix}' ---")
        print(f"Rank in Dense English: {rank_eng}")
        print(f"Rank in Sparse SPLADE: {rank_sparse}")
        print(f"Rank after Reranking: {rank_rerank}")
        
        print("\nTop 5 Reranked Results:")
        for i in range(5):
            point, score = reranked[i]
            print(f"{i+1}. Score: {score:.4f} | ID: {point.id} | Content: {point.payload.get('content')[:100]}...")

if __name__ == "__main__":
    analyze_miss()
