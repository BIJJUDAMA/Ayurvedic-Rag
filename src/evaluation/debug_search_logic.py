import os
import sys
import json
import logging
from qdrant_client import QdrantClient
from rich.console import Console

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.retriever.search_engine import AyurvedaSearchEngine

# Setup logging
logging.basicConfig(level=logging.INFO)
console = Console()

def debug_search_engine():
    client = QdrantClient(host='localhost', port=6333)
    engine = AyurvedaSearchEngine(client)
    
    # Query 3 from dataset.json
    query = "signs and symptoms indicating death within 3 to 7 days"
    original_user_query = "What are the specific physical signs and symptoms that indicate a patient is likely to die within 3 to 7 days, according to ancient Ayurvedic observations?"
    expanded_queries = ["marana lakshana"]
    intent_filter = "Nidana"
    
    print(f"\n--- DEBUGGING SEARCH ENGINE DIRECTLY ---")
    
    results = engine.search(
        original_query=query,
        expanded_queries=expanded_queries,
        top_n=15,
        intent_filter=intent_filter,
        original_user_query=original_user_query
    )
    
    print(f"Results Count: {len(results)}")
    if len(results) > 0:
        print("Top 5 Results:")
        for i, res in enumerate(results[:5]):
            print(f"{i+1}. Score: {res['score']:.4f} | ID: {res['id']} | Content: {res['text'][:100]}...")
    else:
        print("NO RESULTS RETURNED!")

if __name__ == "__main__":
    debug_search_engine()
