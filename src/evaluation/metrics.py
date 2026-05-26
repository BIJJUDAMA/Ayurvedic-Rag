import re
import json
import logging
import os
import numpy as np
import random
from typing import List, Dict, Any, Optional, Tuple
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from rich.table import Table
from rich import box
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Setup logging
logger = logging.getLogger("VaidyaMetrics")
console = Console()

def normalize_id(text: str) -> str:
    """Stable identifier normalization for string-based fuzzy matching."""
    text = str(text).lower()
    text = re.sub(r'[#\-]', '', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()

def semantic_similarity_match(expected: str, retrieved: str, search_engine: Any, threshold: float = 0.85) -> bool:
    """Calculates cosine similarity between embeddings using the GPU Sidecar."""
    if not search_engine or not search_engine.model:
        return False
    
    query_prefix = "query: "
    try:
        # Use search_engine.model (RemoteEmbedder) directly
        v1 = search_engine.model.encode(f"{query_prefix}{expected}")
        v2 = search_engine.model.encode(f"{query_prefix}{retrieved}")
        
        similarity = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        return similarity > threshold
    except:
        return False

def cross_encoder_match(expected: str, retrieved: str, search_engine: Any, threshold: float = 0.7) -> bool:
    """Uses Cross-Encoder (reranker) to score the relationship between two terms."""
    if not search_engine or not search_engine.model:
        return False
    try:
        scores = search_engine.model.rerank(query=expected, documents=[retrieved])
        return scores[0] > threshold if scores else False
    except:
        return False

def is_match(expected_id: str, 
             expected_context: str,
             retrieved_item: Dict[str, Any], 
             search_engine: Optional[Any] = None) -> bool:
    """
    High-Fidelity Match Cascade.
    Checks for exact ID matches first, then falls back to semantic context validation.
    """
    retrieved_id = str(retrieved_item.get("id"))
    retrieved_text = retrieved_item.get("text", "")
    retrieved_title = retrieved_item.get("title", "")
    is_expanded = retrieved_item.get("metadata", {}).get("is_context_expanded", False)

    # 1. Exact ID Match (Direct Hit)
    if expected_id == retrieved_id:
        return True

    # 2. String Normalization (Fuzzy Title Match)
    norm_expected = normalize_id(expected_id)
    norm_retrieved = normalize_id(retrieved_title)
    if norm_expected and norm_retrieved and (norm_expected == norm_retrieved):
        return True
    
    if not search_engine or not expected_context:
        return False

    # 3. Semantic Context Match (E5)
    # If the retrieved text (potentially expanded) is semantically aligned with the ground truth, it's a match.
    # We use a slightly higher threshold for expanded context to ensure the core answer is present.
    threshold = 0.94 if is_expanded else 0.92
    if semantic_similarity_match(expected_context, retrieved_text, search_engine, threshold=threshold):
        return True

    # 4. Cross-Encoder (BGE) 
    # Validates if the retrieved chunk answers the query
    if cross_encoder_match(expected_context, retrieved_text, search_engine, threshold=0.85):
        return True
        
    return False

def get_sanskrit_density(text: str) -> float:
    """Calculates the ratio of Devanagari characters to total characters."""
    if not text: return 0.0
    devanagari_chars = len(re.findall(r'[\u0900-\u097F]', text))
    total_chars = len(text)
    return devanagari_chars / total_chars if total_chars > 0 else 0.0

def calculate_search_metrics(results: List[Dict[str, Any]], 
                            expected_id: str, 
                            expected_context: str,
                            search_engine: Optional[Any] = None) -> Dict[str, Any]:
    found_rank = -1
    for rank, r in enumerate(results):
        if is_match(expected_id, expected_context, r, search_engine):
            found_rank = rank
            break
    
    # Structural: Hierarchical Specificity
    levels = [r.get("metadata", {}).get("level", "unknown") for r in results]
    specificity = {lvl: levels.count(lvl) for lvl in set(levels)}
    
    # Structural: Sequence Continuity (N-Linkage)
    continuity_hits = 0
    retrieved_ids = {str(r.get("id")) for r in results}
    for r in results:
        next_id = r.get("metadata", {}).get("next_id")
        prev_id = r.get("metadata", {}).get("prev_id")
        if (next_id and str(next_id) in retrieved_ids) or (prev_id and str(prev_id) in retrieved_ids):
            continuity_hits += 1
    
    # Multi-lingual: Sanskrit Density
    avg_sanskrit_density = np.mean([get_sanskrit_density(r.get("text", "")) for r in results]) if results else 0.0
    
    # Retrieval Health: Score Variance
    scores = [r.get("score", 0) for r in results]
    score_variance = np.var(scores) if len(scores) > 1 else 0.0
    
    return {
        "hit_at_5": 1 if 0 <= found_rank < 5 else 0,
        "hit_at_10": 1 if 0 <= found_rank < 10 else 0,
        "mrr": 1.0 / (found_rank + 1) if found_rank >= 0 else 0.0,
        "specificity": specificity,
        "continuity_ratio": continuity_hits / len(results) if results else 0.0,
        "sanskrit_density": avg_sanskrit_density,
        "score_variance": score_variance,
        "results_count": len(results)
    }

# --- NEW STRUCTURAL & COHESION METRICS ---

def validate_payload_completeness(client: QdrantClient, collection: str, limit: int = 500) -> float:
    """Checks for presence of mandatory metadata keys across the collection."""
    res, _ = client.scroll(collection_name=collection, limit=limit, with_payload=True)
    if not res: return 0.0
    
    mandatory_keys = {"source_treatise", "level", "content"}
    complete_nodes = 0
    for point in res:
        if all(key in point.payload for key in mandatory_keys):
            complete_nodes += 1
            
    return complete_nodes / len(res)

def validate_tree_integrity(client: QdrantClient, collection: str, limit: int = 500) -> float:
    """Checks what percentage of nodes have valid, existing parent_ids."""
    res, _ = client.scroll(collection_name=collection, limit=limit, with_payload=True)
    if not res: return 0.0
    
    valid_links = 0
    total_links = 0
    
    for point in res:
        parent_id = point.payload.get("parent_id")
        if parent_id and parent_id != "root":
            total_links += 1
            # Check if parent exists
            exists = client.retrieve(collection_name=collection, ids=[parent_id])
            if exists: valid_links += 1
            
    return (valid_links / total_links) if total_links > 0 else 1.0

def validate_sequential_integrity(client: QdrantClient, collection: str, limit: int = 500) -> float:
    """Checks if 'next_id' pointers are valid and lead to existing points."""
    # Specifically target 'verse' or 'section' levels where sequentiality is expected
    res, _ = client.scroll(
        collection_name=collection, 
        scroll_filter=models.Filter(
            must=[models.FieldCondition(key="level", match=models.MatchAny(any=["verse", "section"]))]
        ),
        limit=limit, 
        with_payload=True
    )
    if not res: return 1.0 # Vacuously true if no sequential nodes found
    
    valid_next = 0
    total_next = 0
    
    for point in res:
        next_id = point.payload.get("next_id")
        if next_id:
            total_next += 1
            exists = client.retrieve(collection_name=collection, ids=[next_id])
            if exists: valid_next += 1
            
    return (valid_next / total_next) if total_next > 0 else 1.0

def calculate_graph_density(client: QdrantClient, collection: str, limit: int = 500) -> float:
    """Measures percentage of chunks with at least one relational link (parent, next, or related)."""
    res, _ = client.scroll(collection_name=collection, limit=limit, with_payload=True)
    if not res: return 0.0
    
    linked_nodes = 0
    for point in res:
        p = point.payload
        if p.get("parent_id") or p.get("next_id") or p.get("prev_id") or p.get("metadata", {}).get("related_nodes"):
            linked_nodes += 1
            
    return linked_nodes / len(res)

def calculate_neighborhood_stability(client: QdrantClient, collection: str, limit: int = 100) -> Dict[str, float]:
    """Measures semantic flow between adjacent chunks (Boundary Sharpness)."""
    res, _ = client.scroll(collection_name=collection, limit=limit, with_payload=True, with_vectors=True)
    if not res: return {"avg_similarity": 0.0, "fragmentation_rate": 0.0}

    similarities = []
    fragmented = 0
    
    for point in res:
        next_id = point.payload.get("next_id")
        if not next_id: continue
        
        neighbor = client.retrieve(collection_name=collection, ids=[next_id], with_vectors=True)
        if not neighbor: continue
        
        v1 = point.vector.get("dense_english")
        v2 = neighbor[0].vector.get("dense_english")
        
        if v1 and v2:
            sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
            similarities.append(sim)
            if sim < 0.4: fragmented += 1

    return {
        "avg_similarity": float(np.mean(similarities)) if similarities else 0.0,
        "fragmentation_rate": (fragmented / len(similarities)) if similarities else 0.0
    }

def calculate_redundancy_score(client: QdrantClient, collection: str, limit: int = 200) -> float:
    """Detects % of chunks with >0.95 similarity (Duplicate Bloat)."""
    res, _ = client.scroll(collection_name=collection, limit=limit, with_vectors=True)
    if not res: return 0.0
    
    vectors = [p.vector.get("dense_english") for p in res if p.vector.get("dense_english")]
    if len(vectors) < 2: return 0.0
    
    duplicates = 0
    pairs_tested = 0
    
    # Sample random pairs to keep it fast
    for _ in range(min(500, len(vectors))):
        i, j = random.sample(range(len(vectors)), 2)
        v1, v2 = vectors[i], vectors[j]
        sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        pairs_tested += 1
        if sim > 0.95: duplicates += 1
        
    return duplicates / pairs_tested

# --- RUNNERS ---

def run_evaluation(engine, gold_dataset_path: str, retriever: Optional[Any] = None):
    """Runs high-fidelity metrics over dataset using context validation."""
    if not os.path.exists(gold_dataset_path):
        console.print(f"[red]Error: Gold dataset not found at {gold_dataset_path}")
        return {}

    with open(gold_dataset_path, 'r', encoding='utf-8') as f:
        gold_data = json.load(f)

    metrics_acc = {
        "recalls_5": [], "recalls_10": [], "mrrs": [],
        "continuities": [], "sanskrit_densities": [], "variances": [],
        "specificities": []
    }

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console, transient=True) as progress:
        task = progress.add_task("[cyan]High-Fidelity Retrieval Audit...", total=len(gold_data))
        
        for item in gold_data:
            query = item.get("query")
            expected_id = item.get("expected_id")
            expected_context = item.get("ground_truth_context", "")

            if not query or not expected_id: continue

            try:
                # AyurvedaSearchEngine.search returns List[Dict]
                # ProductionAgentWrapper.search (in run_eval.py) returns (List[Dict], str)
                search_output = engine.search(query, top_n=20)
                
                # Unpack if tuple (results, answer)
                if isinstance(search_output, tuple):
                    search_results = search_output[0]
                else:
                    search_results = search_output

                # Use retriever for scoring if provided, otherwise fallback to search engine
                scoring_engine = retriever or engine
                m = calculate_search_metrics(search_results, expected_id, expected_context, scoring_engine)
                
                metrics_acc["recalls_5"].append(m["hit_at_5"])
                metrics_acc["recalls_10"].append(m["hit_at_10"])
                metrics_acc["mrrs"].append(m["mrr"])
                metrics_acc["continuities"].append(m["continuity_ratio"])
                metrics_acc["sanskrit_densities"].append(m["sanskrit_density"])
                metrics_acc["variances"].append(m["score_variance"])
                metrics_acc["specificities"].append(m["specificity"])

            except Exception as e:
                logger.error(f"Error evaluating query '{query}': {e}")
            progress.advance(task)

    # Aggregate specificities
    total_specificity = {}
    for spec in metrics_acc["specificities"]:
        for k, v in spec.items():
            total_specificity[k] = total_specificity.get(k, 0) + v

    return {
        "recall_5": np.mean(metrics_acc["recalls_5"]) if metrics_acc["recalls_5"] else 0,
        "recall_10": np.mean(metrics_acc["recalls_10"]) if metrics_acc["recalls_10"] else 0,
        "mrr": np.mean(metrics_acc["mrrs"]) if metrics_acc["mrrs"] else 0,
        "avg_continuity": np.mean(metrics_acc["continuities"]) if metrics_acc["continuities"] else 0,
        "avg_sanskrit_density": np.mean(metrics_acc["sanskrit_densities"]) if metrics_acc["sanskrit_densities"] else 0,
        "avg_variance": np.mean(metrics_acc["variances"]) if metrics_acc["variances"] else 0,
        "specificity": total_specificity
    }

if __name__ == "__main__":
    from src.retriever.search_engine import AyurvedaSearchEngine
    from qdrant_client import QdrantClient
    
    # 1. Initialize
    client = QdrantClient(host="localhost", port=6333)
    engine = AyurvedaSearchEngine(client=client)
    dataset_path = os.path.join("src", "evaluation", "dataset.json")
    
    console.print("\n[bold cyan]─── Ayurveda Pure Evaluation Stack ───[/]\n")
    
    # 2. Retrieval Quality (IR)
    ir_results = run_evaluation(engine, dataset_path)
    
    # 3. Structural & Cohesion Analysis
    with console.status("[bold yellow]Analyzing Database Health (Non-LLM)..."):
        tree_health = validate_tree_integrity(client, "ayurveda_rag")
        seq_health = validate_sequential_integrity(client, "ayurveda_rag")
        payload_health = validate_payload_completeness(client, "ayurveda_rag")
        graph_density = calculate_graph_density(client, "ayurveda_rag")
        cohesion = calculate_neighborhood_stability(client, "ayurveda_rag")
        redundancy = calculate_redundancy_score(client, "ayurveda_rag")

    # 4. Final Report
    report = Table(title="[bold green]System Benchmark Results", box=box.ROUNDED, border_style="cyan")
    report.add_column("Category", style="dim")
    report.add_column("Metric", style="bold white")
    report.add_column("Value", justify="right", style="bold yellow")
    report.add_column("Status", justify="center")

    def get_status(val, low, high):
        if val < low: return "[red]FAIL"
        if val < high: return "[yellow]WARN"
        return "[green]PASS"

    # IR Metrics
    report.add_row("Retrieval", "Recall @ 5", f"{ir_results.get('recall_5', 0):.4f}", get_status(ir_results.get('recall_5', 0), 0.5, 0.7))
    report.add_row("Retrieval", "Recall @ 10", f"{ir_results.get('recall_10', 0):.4f}", get_status(ir_results.get('recall_10', 0), 0.6, 0.8))
    report.add_row("Retrieval", "MRR (Ranking)", f"{ir_results.get('mrr', 0):.4f}", get_status(ir_results.get('mrr', 0), 0.3, 0.5))
    report.add_row("Retrieval", "Sequence Continuity", f"{ir_results.get('avg_continuity', 0)*100:.1f}%", get_status(ir_results.get('avg_continuity', 0), 0.4, 0.6))
    
    report.add_section()
    
    # Multi-lingual
    report.add_row("Semantic", "Sanskrit Density", f"{ir_results.get('avg_sanskrit_density', 0)*100:.1f}%", "[dim]N/A")
    report.add_row("Semantic", "Score Variance", f"{ir_results.get('avg_variance', 0):.4f}", "[dim]N/A")
    
    report.add_section()

    # Structural
    report.add_row("Structure", "Tree Integrity", f"{tree_health*100:.1f}%", "[green]PASS" if tree_health > 0.99 else "[red]ORPHANS")
    report.add_row("Structure", "Seq. Integrity", f"{seq_health*100:.1f}%", "[green]PASS" if seq_health > 0.90 else "[yellow]BROKEN")
    report.add_row("Structure", "Payload Completeness", f"{payload_health*100:.1f}%", "[green]PASS" if payload_health > 0.95 else "[red]INCOMPLETE")
    report.add_row("Structure", "Graph Density", f"{graph_density*100:.1f}%", "[green]PASS" if graph_density > 0.95 else "[red]ISOLATED")
    report.add_row("Cohesion", "Avg. Flow (Sim)", f"{cohesion['avg_similarity']:.3f}", "[green]PASS" if 0.5 < cohesion['avg_similarity'] < 0.9 else "[yellow]STIFF")
    report.add_row("Cohesion", "Fragmentation", f"{cohesion['fragmentation_rate']*100:.1f}%", "[green]PASS" if cohesion['fragmentation_rate'] < 0.1 else "[red]HIGH")
    report.add_row("Bloat", "Redundancy", f"{redundancy*100:.1f}%", "[green]PASS" if redundancy < 0.05 else "[yellow]BLOAT")

    console.print(report)
    
    # Specificity breakdown
    spec = ir_results.get("specificity", {})
    total_spec = sum(spec.values())
    if total_spec > 0:
        spec_table = Table(title="[dim]Hierarchical Specificity Breakdown", box=box.SIMPLE_HEAD)
        spec_table.add_column("Level", style="cyan")
        spec_table.add_column("Count", justify="right")
        spec_table.add_column("Percentage", justify="right", style="magenta")
        for lvl, count in sorted(spec.items(), key=lambda x: x[1], reverse=True):
            spec_table.add_row(lvl, str(count), f"{(count/total_spec)*100:.1f}%")
        console.print(spec_table)

    console.print("\n[dim]Analysis complete. All metrics derived mathematically from vector space and hierarchy.[/]\n")

