import json
import os
from typing import List, Dict, Any

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def save_jsonl(path: str, data: List[Dict[str, Any]]):
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")

def cross_link():
    books = ["charak_samhita", "shusrut_samhita", "astanga_hridaya"]
    all_data = {}
    term_to_ids = {}

    print("Loading data and indexing terms...")
    for book in books:
        path = os.path.join("processed-books", book, "vectors.jsonl")
        if not os.path.exists(path):
            print(f"Warning: {path} not found.")
            continue
        
        chunks = load_jsonl(path)
        all_data[book] = chunks
        
        for chunk in chunks:
            # Extract terms from title, metadata, or glossary stubs
            terms = set()
            if chunk.get("level") in ["stub_glossary", "stub_botanical"]:
                terms.add(chunk["title"].lower())
            
            # Also check metadata technical terms if present
            meta_terms = chunk.get("metadata", {}).get("technical_terms", [])
            for t in meta_terms:
                terms.add(t.lower())
                
            for term in terms:
                if term not in term_to_ids:
                    term_to_ids[term] = []
                term_to_ids[term].append(chunk["id"])

    print(f"Found {len(term_to_ids)} terms. Injecting cross-links...")
    for book, chunks in all_data.items():
        for chunk in chunks:
            node_id = chunk["id"]
            related = set()
            
            # Find terms associated with this chunk
            chunk_terms = set()
            if chunk.get("level") in ["stub_glossary", "stub_botanical"]:
                chunk_terms.add(chunk["title"].lower())
            
            meta_terms = chunk.get("metadata", {}).get("technical_terms", [])
            for t in meta_terms:
                chunk_terms.add(t.lower())
                
            for term in chunk_terms:
                # Add all other nodes sharing this term
                for other_id in term_to_ids.get(term, []):
                    if other_id != node_id:
                        related.add(other_id)
            
            if related:
                if "metadata" not in chunk:
                    chunk["metadata"] = {}
                chunk["metadata"]["related_nodes"] = list(related)

    print("Saving enriched artifacts...")
    for book, chunks in all_data.items():
        path = os.path.join("processed-books", book, "vectors.jsonl")
        save_jsonl(path, chunks)
        print(f"Updated {path}")

if __name__ == "__main__":
    cross_link()
