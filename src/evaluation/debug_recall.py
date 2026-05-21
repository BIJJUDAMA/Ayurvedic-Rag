import os
import sys
import json
import logging
from qdrant_client import QdrantClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.retriever.vaidya_engine import AyurvedaRetriever

# Setup logging
logging.basicConfig(level=logging.INFO)
console = Console()

def debug_all_queries():
    retriever = AyurvedaRetriever(console=console)
    
    with open(GOLD_DATASET_PATH, 'r', encoding='utf-8') as f:
        gold_data = json.load(f)
    
    results_table = Table(title="Overall Retrieval Recall Debug")
    results_table.add_column("Query ID", justify="right")
    results_table.add_column("Found At", justify="right")
    results_table.add_column("Status")
    
    for i, item in enumerate(gold_data):
        query = item['query']
        expected_id = item['expected_id']
        
        results = retriever.search_engine.search(query, top_n=50)
        found_at = -1
        for rank, res in enumerate(results):
            if res['id'] == expected_id:
                found_at = rank + 1
                break
        
        status = "[green]PASS[/]" if 0 < found_at <= 5 else "[yellow]FAIL (Top 50)[/]" if found_at > 0 else "[red]MISS[/]"
        results_table.add_row(str(i+1), str(found_at) if found_at > 0 else "N/A", status)
    
    console.print(results_table)

if __name__ == "__main__":
    GOLD_DATASET_PATH = os.path.join("src", "evaluation", "dataset.json")
    debug_all_queries()

