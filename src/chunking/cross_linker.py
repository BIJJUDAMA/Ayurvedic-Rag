import json
import os
import csv
from typing import List, Dict, Any

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def save_jsonl(path: str, data: List[Dict[str, Any]]):
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")

def load_graph_entities() -> Dict[str, str]:
    """Loads entities from Neo4j CSV for cross-referencing."""
    nodes_path = os.path.join("graph", "data", "graph_nodes.csv")
    if not os.path.exists(nodes_path):
        print(f"Warning: Graph nodes not found at {nodes_path}")
        return {}
    
    entities = {} # name.lower() -> id
    try:
        with open(nodes_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row['name'].lower()
                entities[name] = row['id']
    except Exception as e:
        print(f"Error loading graph entities: {e}")
    return entities

def cross_link():
    books = ["charak_samhita", "shusrut_samhita", "astanga_hridaya"]
    all_data = {}
    term_to_ids = {}

    graph_entities = load_graph_entities()
    print(f"Loaded {len(graph_entities)} clinical entities from knowledge graph.")

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
            
            # 1. Internal Cross-Linker (Term-based)
            chunk_terms = set()
            if chunk.get("level") in ["stub_glossary", "stub_botanical"]:
                chunk_terms.add(chunk["title"].lower())
            
            meta_terms = chunk.get("metadata", {}).get("technical_terms", [])
            for t in meta_terms:
                chunk_terms.add(t.lower())
                
            for term in chunk_terms:
                for other_id in term_to_ids.get(term, []):
                    if other_id != node_id:
                        related.add(other_id)
            
            if related:
                if "metadata" not in chunk: chunk["metadata"] = {}
                chunk["metadata"]["related_nodes"] = list(related)

            # 2. Knowledge Graph Linker (Entity-based)
            neo4j_links = []
            content_lower = chunk.get("content", "").lower()
            title_lower = chunk.get("title", "").lower()
            
            # Check tech terms first (high precision)
            for t in meta_terms:
                t_low = t.lower()
                if t_low in graph_entities:
                    neo4j_links.append(graph_entities[t_low])
            
            # Scan content (high recall)
            for ent_name, ent_id in graph_entities.items():
                if len(ent_name) > 5: # Only scan longer names to avoid false positives in text
                    if ent_name in content_lower or ent_name in title_lower:
                        neo4j_links.append(ent_id)
            
            if neo4j_links:
                if "metadata" not in chunk: chunk["metadata"] = {}
                chunk["metadata"]["neo4j_entities"] = list(set(neo4j_links))

    print("Saving enriched artifacts...")
    for book, chunks in all_data.items():
        path = os.path.join("processed-books", book, "vectors.jsonl")
        save_jsonl(path, chunks)
        print(f"Updated {path}")

if __name__ == "__main__":
    cross_link()
