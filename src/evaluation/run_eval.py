import os
import sys
import logging
import json
from typing import Optional
from qdrant_client import QdrantClient

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.logging import RichHandler
from rich.table import Table
from rich import box
from rich.layout import Layout
from rich.columns import Columns

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.retriever.vaidya_engine import AyurvedaRetriever
from src.evaluation.metrics import run_evaluation
from src.evaluation.ragas_eval import run_ragas_evaluation

# Setup Rich Console
console = Console()

# Setup logging with RichHandler
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console, show_path=False)]
)
logger = logging.getLogger("AyurvedaRAGEval")

# Constants
GOLD_DATASET_PATH = os.path.join("src", "evaluation", "dataset.json")

def print_final_health_report(classical: dict, semantic: Optional[dict]):
    """Prints a consolidated project health report."""
    semantic = semantic or {}
    console.print("\n" + "="*60)
    console.print(Panel(
        "[bold gold3]AYURVEDA RAG: SYSTEM HEALTH REPORT[/]",
        subtitle="Consolidated Scholarly Performance Data",
        border_style="gold3",
        box=box.DOUBLE,
        expand=False
    ))

    # Classical Column
    c_table = Table(title="[cyan]Search Engine (Retrieval)[/]", box=box.SIMPLE)
    c_table.add_column("Metric", style="dim")
    c_table.add_column("Value", justify="right", style="bold yellow")
    c_table.add_row("Recall_Top_5", f"{classical.get('recall_5', 0):.4f}")
    c_table.add_row("Recall_Top_10", f"{classical.get('recall_10', 0):.4f}")
    c_table.add_row("MRR_Quality", f"{classical.get('mrr', 0):.4f}")

    # Semantic Column
    s_table = Table(title="[magenta]LLM Judge (Synthesis)[/]", box=box.SIMPLE)
    s_table.add_column("Metric", style="dim")
    s_table.add_column("Value", justify="right", style="bold yellow")
    s_table.add_row("Context Precision", f"{semantic.get('context_precision', 0) or 0:.4f}")
    s_table.add_row("Context Recall", f"{semantic.get('context_recall', 0) or 0:.4f}")
    s_table.add_row("Faithfulness", f"{semantic.get('faithfulness', 0) or 0:.4f}")
    s_table.add_row("Answer Relevancy", f"{semantic.get('answer_relevancy', 0) or 0:.4f}")

    console.print(Columns([c_table, s_table], equal=True, expand=True))
    
    # Final Interpretation
    mrr = classical.get('mrr', 0)
    precision = semantic.get('context_precision', 0) or 0
    faithfulness = semantic.get('faithfulness', 0) or 0
    
    status = "[bold green]EXCELLENT[/]" if mrr > 0.4 and precision > 0.6 and faithfulness > 0.8 else "[bold yellow]STABLE[/]" if mrr > 0.2 else "[bold red]CRITICAL (Needs Tuning)[/]"
    
    console.print(Panel(
        f"Overall System Status: {status}\n"
        "[dim]Note: Metrics are based on the 100% Production Sync Agent loop.[/]",
        border_style="dim"
    ))
    console.print("="*60 + "\n")

def main():
    console.print(Panel.fit(
        "[bold gold3]AYURVEDA RAG[/] - [bold cyan]100% Production Sync Evaluation[/]",
        subtitle="Multi-Vector Hybrid Search Loop",
        border_style="cyan",
        box=box.DOUBLE
    ))

    # 1. Initialize Retriever
    retriever = None
    with console.status("[bold cyan]Loading Scholarly Pipeline..."):
        try:
            retriever = AyurvedaRetriever(console=console)
            console.print("[bold green]OK[/] Components Ready.")
        except Exception as e:
            console.print(f"[bold red]FAIL[/] Critical Error: {e}")
            return

    class ProductionAgentWrapper:
        def __init__(self, retriever):
            self.retriever = retriever
        
        def search(self, query, top_k=20):
            """
            Executes the full agentic loop (Router + Tool Calls + Synthesis).
            Returns (hits, answer) to satisfy both classical and Ragas metrics.
            """
            hits, answer = self.retriever.generate_answer(query)
            # generate_answer returns sorted_hits as List[Tuple[doc_id, hit_dict]]
            # We return just the hit_dicts for compatibility with existing metrics logic
            hit_dicts = [h[1] for h in hits]
            return hit_dicts, answer

    console.print(f"\n[bold cyan]▶ Starting 100% Production Sync Evaluation...[/]")
    wrapper = ProductionAgentWrapper(retriever)
    
    # Run and Collect Classical Metrics
    # Pass the retriever to use its sub-components (LLM, Embedder) for scoring
    classical_results = run_evaluation(wrapper, GOLD_DATASET_PATH, retriever=retriever)
    
    # Run and Collect Ragas Metrics
    semantic_results = run_ragas_evaluation(wrapper, GOLD_DATASET_PATH)

    # 3. PRINT FINAL CONSOLIDATED SUMMARY
    print_final_health_report(classical_results, semantic_results)

if __name__ == "__main__":
    main()
