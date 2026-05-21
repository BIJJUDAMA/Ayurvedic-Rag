import os
import sys
import json
import logging
from rich.console import Console

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.retriever.vaidya_engine import AyurvedaRetriever
from src.evaluation.metrics import calculate_search_metrics

# Setup logging
logging.basicConfig(level=logging.INFO)
console = Console()

def debug_query_3():
    retriever = AyurvedaRetriever(console=console)
    
    # Query 3 from dataset.json (index 2)
    with open('src/evaluation/dataset.json', 'r', encoding='utf-8') as f:
        gold_data = json.load(f)
    
    item = gold_data[2]
    query = item['query']
    expected_id = item['expected_id']
    
    print(f"\n--- DEBUGGING QUERY 3 ---")
    print(f"Query: {query}")
    print(f"Expected ID: {expected_id}")
    
    hits, answer = retriever.generate_answer(query)
    
    print(f"\nAnswer:\n{answer}")
    
    result_ids = []
    for hit_id, res in hits:
        title = res.get('title') or ""
        result_ids.append(f"{hit_id}|{title}")
    
    r5, r10, mrr = calculate_search_metrics(result_ids, expected_id, retriever)
    
    print(f"\nRecall@5: {r5}")
    print(f"Found At Rank: {1/mrr if mrr > 0 else 'N/A'}")
    
    print("\nTop 5 Retrieved IDs:")
    for i in range(min(5, len(result_ids))):
        print(f"{i+1}. {result_ids[i]}")

if __name__ == "__main__":
    debug_query_3()
