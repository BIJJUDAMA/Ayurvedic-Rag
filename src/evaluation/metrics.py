import re
import json
import logging
import os
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from rich.table import Table
from rich import box
from google.genai import types

# Setup logging
logger = logging.getLogger("VaidyaMetrics")
console = Console()

def normalize_id(text: str) -> str:
    """
    STABLE IDENTIFIER NORMALIZATION:
    Removes Markdown headers, punctuation, dashes, and extra whitespace to create a clean 'Slug'.
    Example: '## Dandalasaka -' -> 'dandalasaka'
    """
    text = str(text).lower()
    # Remove markdown headers (##), dashes (-), and non-alphanumeric chars (except space)
    text = re.sub(r'[#\-]', '', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()

def llm_judge_match(expected: str, retrieved: str, retriever: Any) -> bool:
    """Uses LLM-as-a-Judge to determine if two terms refer to the same Ayurvedic concept."""
    if not retriever or not retriever.llm_client:
        return False
    
    prompt = f"""
    Are the following two Ayurvedic identifiers referring to the same condition, concept, or term?
    Expected: "{expected}"
    Retrieved: "{retrieved}"
    
    Consider minor spelling differences, OCR noise (like ## or numbers), and synonyms.
    Answer ONLY with "YES" or "NO".
    """
    
    try:
        response = retriever.llm_client.models.generate_content(
            model=retriever.model_id,
            contents=prompt
        )
        answer = response.text.strip().upper()
        return "YES" in answer
    except Exception as e:
        logger.error(f"LLM Judge error: {e}")
        return False

def cross_encoder_match(expected: str, retrieved: str, retriever: Any, threshold: float = 0.7) -> bool:
    """Uses Cross-Encoder (reranker) to score the relationship between two terms."""
    if not retriever or not retriever.model:
        return False
    
    try:
        # We use rerank as a way to score the pair
        scores = retriever.model.rerank(query=expected, documents=[retrieved])
        if scores and scores[0] > threshold:
            return True
        return False
    except Exception as e:
        logger.error(f"Cross-Encoder error: {e}")
        return False

def semantic_similarity_match(expected: str, retrieved: str, retriever: Any, threshold: float = 0.85) -> bool:
    """Calculates cosine similarity between embeddings of the two terms."""
    if not retriever or not retriever.model:
        return False
    
    # E5 Prefix requirement: "query: " for retrieval-style matching
    query_prefix = "query: "
    
    try:
        v1 = retriever.model.encode(f"{query_prefix}{expected}")
        v2 = retriever.model.encode(f"{query_prefix}{retrieved}")
        
        # Cosine similarity
        similarity = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        return similarity > threshold
    except Exception as e:
        logger.error(f"Semantic similarity error: {e}")
        return False

def is_match(expected_id: str, retrieved_title: str, retriever: Optional[Any] = None) -> bool:
    """Combines multiple matching strategies for maximum robustness."""
    # Parse the retrieved string (chunk_id|title)
    parts = retrieved_title.split("|", 1)
    retrieved_chunk_id = parts[0] if parts else ""
    actual_title = parts[1] if len(parts) > 1 else retrieved_title

    # 1. Exact ID Match (Fastest and most accurate if expected_id is a UUID)
    if expected_id == retrieved_chunk_id:
        return True

    # 2. Simple Normalization (Fast Pass on Title)
    norm_expected = normalize_id(expected_id)
    norm_retrieved = normalize_id(actual_title)
    
    if norm_expected and norm_retrieved:
        if norm_expected == norm_retrieved or norm_expected in norm_retrieved or norm_retrieved in norm_expected:
            return True
    
    # If no retriever provided, we can only do string matching
    if not retriever:
        return False

    # 3. Semantic Similarity (Fast Vector Pass)
    if semantic_similarity_match(expected_id, actual_title, retriever):
        return True

    # 4. Cross-Encoder (Slower, High Precision)
    if cross_encoder_match(expected_id, actual_title, retriever):
        return True

    # 5. LLM Judge (Slowest, Last Resort)
    if llm_judge_match(expected_id, actual_title, retriever):
        return True
        
    return False

def calculate_search_metrics(results: List[str], expected_id: str, retriever: Optional[Any] = None) -> Tuple[int, int, float]:
    """Calculates Recall@5, Recall@10, and MRR in a single pass for consistency."""
    found_rank = -1
    for rank, r in enumerate(results):
        if is_match(expected_id, r, retriever):
            found_rank = rank
            break
    
    r5 = 1 if 0 <= found_rank < 5 else 0
    r10 = 1 if 0 <= found_rank < 10 else 0
    mrr = 1.0 / (found_rank + 1) if found_rank >= 0 else 0.0
    return r5, r10, mrr

def run_evaluation(engine, gold_dataset_path: str, retriever: Optional[Any] = None):
    """Runs evaluation over the entire gold dataset."""
    if not os.path.exists(gold_dataset_path):
        logger.error(f"Gold dataset not found at {gold_dataset_path}")
        return

    try:
        with open(gold_dataset_path, 'r', encoding='utf-8') as f:
            gold_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode gold dataset JSON: {e}")
        return

    logger.info(f"Starting evaluation on {len(gold_data)} queries...")

    recalls_at_5 = []
    recalls_at_10 = []
    mrrs = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True 
    ) as progress:
        task = progress.add_task("[cyan]Evaluating Classical Metrics...", total=len(gold_data))
        
        for item in gold_data:
            query = item.get("query")
            expected_id = item.get("expected_id")
            
            if not query or not expected_id:
                logger.warning(f"Skipping malformed entry: {item}")
                progress.advance(task)
                continue

            progress.update(task, description=f"[cyan]Query:[/] [dim]{query[:50]}...[/]")

            try:
                # Perform search (now returns (hit_dicts, answer))
                search_results, _ = engine.search(query, top_k=20)
                
                # Robust ID extraction
                result_ids = []
                for res in search_results:
                    if isinstance(res, dict):
                        # Use the actual chunk ID for matching, fallback to title
                        chunk_id = res.get('id')
                        title = res.get('title') or res.get('chapter_title') or res.get('section_title') or ""
                        # Store both ID and Title to allow the cascade matcher to try both
                        result_ids.append(f"{chunk_id}|{title}")
                    else:
                        result_ids.append(str(res).strip())

                r5, r10, mrr = calculate_search_metrics(result_ids, expected_id, retriever)
                recalls_at_5.append(r5)
                recalls_at_10.append(r10)
                mrrs.append(mrr)
                
                if r5 == 0:
                    logger.warning(f"MISS! Expected ID: {expected_id}")
                    logger.warning(f"Top 5 Retrieved: {[r.split('|')[0] for r in result_ids[:5]]}")
                    logger.warning(f"Query: {query}")
            except Exception as e:
                logger.error(f"Error evaluating query '{query}': {e}")
            
            progress.advance(task)

    # Aggregate Results
    if recalls_at_5:
        # Disable logging temporarily to prevent interleaving with the table print
        logging.disable(logging.CRITICAL)
        
        results_table = Table(title="[bold green]Classical Retrieval Summary", box=box.DOUBLE_EDGE, border_style="green")
        results_table.add_column("Metric", style="cyan")
        results_table.add_column("Value", justify="right", style="bold yellow")
        
        results_table.add_row("Recall_Top_5", f"{np.mean(recalls_at_5):.4f}")
        results_table.add_row("Recall_Top_10", f"{np.mean(recalls_at_10):.4f}")
        results_table.add_row("MRR_Ranking_Quality", f"{np.mean(mrrs):.4f}")
        
        console.print("\n")
        console.print(results_table)
        
        # Re-enable logging
        logging.disable(logging.NOTSET)
        
        return {
            "recall_5": np.mean(recalls_at_5),
            "recall_10": np.mean(recalls_at_10),
            "mrr": np.mean(mrrs)
        }
    else:
        logger.warning("No evaluation results were recorded.")
        return {}

if __name__ == "__main__":
    pass
