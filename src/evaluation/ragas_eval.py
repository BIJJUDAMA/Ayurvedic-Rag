import os
import json
import logging
import pandas as pd
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import context_precision, context_recall, faithfulness, answer_relevancy
from google.genai import types
from dotenv import load_dotenv

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import box
from typing import Any, List

# Setup logging
logger = logging.getLogger("VaidyaRagas")
console = Console()

load_dotenv()

# --- Custom Wrappers to avoid Ragas/LangChain Version Conflicts ---
from langchain_core.embeddings import Embeddings
from ragas.llms.base import LangchainLLMWrapper as _LangchainLLMWrapper
from ragas.embeddings.base import LangchainEmbeddingsWrapper as _LangchainEmbeddingsWrapper

class LocalEmbeddingsWrapper(Embeddings):
    """Bridges RemoteEmbedder to LangChain Embeddings interface."""
    def __init__(self, remote_model):
        self._remote_model = remote_model
        # Ragas/Pydantic expects 'model' to be a string name for usage tracking
        self.model = "multilingual-e5-large" 
        
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        import numpy as np
        embeddings = self._remote_model.encode(texts)
        if isinstance(embeddings, np.ndarray):
            return embeddings.tolist()
        return embeddings
        
    def embed_query(self, text: str) -> List[float]:
        import numpy as np
        embedding = self._remote_model.encode(text)
        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        return embedding

class RobustGeminiLLM(_LangchainLLMWrapper):
    """Wrapper to catch and repair common Gemini output parsing errors."""
    def generate_text(self, prompt: Any, n: int = 1, temperature: float = 1e-8) -> Any:
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res = super().generate_text(prompt, n, temperature)
                
                # REPAIR LOGIC: Clean response text for Pydantic
                if hasattr(res, 'generations') and res.generations:
                    for gen_list in res.generations:
                        for gen in gen_list:
                            # Remove markdown code blocks if present
                            text = gen.text.strip()
                            if text.startswith("```json"):
                                text = text[7:]
                            if text.endswith("```"):
                                text = text[:-3]
                            gen.text = text.strip()
                return res
                
            except Exception as e:
                err_msg = str(e).lower()
                if "503" in err_msg or "rate_limit" in err_msg or "overloaded" in err_msg:
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"Gemini API Overloaded (503). Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                    
                if "text" in err_msg or "outputparserexception" in err_msg:
                    logger.warning(f"Repairing LLM judge output for parsing error: {e}")
                    temperature = 0.1 # Slight jitter to force fresh JSON structure
                    continue
                raise e
        return super().generate_text(prompt, n, temperature)

def run_ragas_evaluation(engine, gold_dataset_path: str):
    """Runs Ragas evaluation (Context Precision/Recall) using Gemini 2.5-flash-lite."""
    
    if not os.path.exists(gold_dataset_path):
        logger.error(f"Gold dataset not found at {gold_dataset_path}")
        return

    try:
        with open(gold_dataset_path, 'r', encoding='utf-8') as f:
            gold_data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading gold dataset: {e}")
        return

    logger.info("Preparing data for Ragas...")
    
    data_samples = {
        "question": [],
        "contexts": [],
        "answer": [],
        "ground_truth": []
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Gathering Agentic Contexts & Answers for Ragas...", total=len(gold_data))
        
        for item in gold_data:
            query = item.get("query")
            # FIX: dataset.json uses 'ground_truth_context'
            ground_truth = item.get("ground_truth_context", "") 
            
            progress.update(task, description=f"[cyan]Ragas Loop:[/] [dim]{query[:50]}...[/]")
            
            try:
                # Perform full agentic search
                search_output = engine.search(query, top_n=5)
                
                if isinstance(search_output, tuple):
                    results, answer = search_output
                else:
                    results, answer = search_output, "NO_ANSWER_PROVIDED"
                
                # Context Formatting: Pure text for string matching metrics
                contexts = []
                for res in results:
                    text = res.get('text') or res.get('metadata', {}).get('content') or str(res)
                    contexts.append(text.strip())
                
                if contexts:
                    data_samples["question"].append(query)
                    data_samples["contexts"].append(contexts)
                    data_samples["answer"].append(answer or "NO_ANSWER_GENERATED")
                    data_samples["ground_truth"].append(ground_truth)
            except Exception as e:
                logger.error(f"Error gathering agent response for query '{query}': {e}")
            
            progress.advance(task)

    if not data_samples["question"]:
        logger.warning("No samples gathered for Ragas evaluation.")
        return

    dataset = Dataset.from_dict(data_samples)

    console.print("[bold blue]▶ Sending to Ragas (LLM-as-a-Judge)...[/] [dim](Evaluating Context + Synthesis)[/]")
    
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment.")

        # Initialize base LangChain models
        gemini_chat = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=api_key,
            temperature=0,
            max_retries=15 # Aggressive retries for 503 errors
        )
        
        # Wrap for Ragas
        ragas_llm = RobustGeminiLLM(langchain_llm=gemini_chat)
        
        local_embeddings = LocalEmbeddingsWrapper(engine.retriever.model)
        ragas_embeddings = _LangchainEmbeddingsWrapper(embeddings=local_embeddings)
        
        # Metric configuration
        faithfulness.llm = ragas_llm
        answer_relevancy.llm = ragas_llm
        context_precision.llm = ragas_llm
        context_recall.llm = ragas_llm
        
        metrics = [context_precision, faithfulness, answer_relevancy]
        if any(gt for gt in data_samples["ground_truth"]):
            metrics.append(context_recall)

        # Run evaluation
        result = evaluate(
            dataset,
            metrics=metrics,
            llm=ragas_llm,
            embeddings=ragas_embeddings
        )
        
        df = result.to_pandas()
        
        results_table = Table(title="[bold green]Ragas Agentic Results", box=box.DOUBLE_EDGE, border_style="green")
        results_table.add_column("Metric", style="cyan")
        results_table.add_column("Value", justify="right", style="bold yellow")
        
        for metric in ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]:
            if metric in df:
                results_table.add_row(metric.replace("_", " ").title(), f"{df[metric].mean():.4f}")
        
        console.print("\n")
        console.print(results_table)
        
        return {
            "context_precision": df['context_precision'].mean() if 'context_precision' in df else None,
            "context_recall": df['context_recall'].mean() if 'context_recall' in df else None,
            "faithfulness": df['faithfulness'].mean() if 'faithfulness' in df else None,
            "answer_relevancy": df['answer_relevancy'].mean() if 'answer_relevancy' in df else None
        }
        
    except Exception as e:
        logger.error(f"Ragas evaluation failed: {e}")
        import traceback
        logger.error(traceback.format_exc()) # Print full traceback to debug the DeprecationHelper issue
        return {}

if __name__ == "__main__":
    pass
