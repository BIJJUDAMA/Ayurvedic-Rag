import os
import json
from qdrant_client import QdrantClient

def check_ids():
    client = QdrantClient(host='localhost', port=6333)
    dataset_path = os.path.join('src', 'evaluation', 'dataset.json')
    
    if not os.path.exists(dataset_path):
        print(f"Dataset not found at {dataset_path}")
        return
        
    with open(dataset_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    ids = [item['expected_id'] for item in data]
    print(f"Checking {len(ids)} IDs...")
    
    res = client.retrieve(collection_name='ayurveda_rag', ids=ids)
    found_ids = [r.id for r in res]
    
    for i, target_id in enumerate(ids):
        exists = target_id in found_ids
        print(f"ID {i+1} ({target_id}): {'FOUND' if exists else 'NOT FOUND'}")
        
    print(f"\nSummary: Found {len(found_ids)} out of {len(ids)}")

if __name__ == "__main__":
    check_ids()
