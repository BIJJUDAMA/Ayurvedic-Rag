"""
Vaidya AI - Interactive Ayurvedic Research CLI
This is the main entry point for the Ayurveda Retriever system.
Enhanced with 'Rich' for professional scholarly visualization.
"""
import sys
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.rule import Rule
from rich.theme import Theme
from rich.box import ROUNDED, DOUBLE

# Load environment variables
load_dotenv()

# Fix path for direct execution
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.retriever.vaidya_engine import AyurvedaRetriever

# Custom theme for Ayurvedic scholarship
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "vaidya": "bold magenta",
    "source": "green",
    "citation": "italic gold3"
})

console = Console(theme=custom_theme)

def main():
    console.print(Panel(
        "[bold vaidya]VAIDYA AI - CLASSICAL AYURVEDA RESEARCH ENGINE[/]\n"
        "[italic]Digital Epistemology & Scholarly Graph-RAG[/]",
        border_style="vaidya",
        box=DOUBLE,
        expand=False
    ))
    
    with console.status("[bold info]Initializing system (loading models & building indices)...[/]"):
        try:
            # Pass our console to the retriever for unified logging
            retriever = AyurvedaRetriever(console=console)
            console.print("[bold green] [OK] System Ready.[/]")
        except Exception as e:
            console.print(f"[bold error] [!] Initialization failed: {e}[/]")
            return

    while True:
        console.print("\n" + "="*50)
        try:
            query = console.input("[bold cyan]Query > [/]").strip()
        except EOFError:
            break
            
        if query.lower() in ['exit', 'quit', 'q']:
            console.print("[vaidya]Exiting. Namaste.[/]")
            break
            
        if not query:
            continue
            
        console.print("="*50 + "\n")
        
        with console.status("[bold vaidya]Vaidya is analyzing classical manuscripts...[/]"):
            try:
                # generate_answer will print real-time tool calls and evidence snippets
                results, answer = retriever.generate_answer(query)
                
                # 1. Handle missing/None answer
                if answer is None:
                    answer = "The scholarly engine failed to provide a text response. Please check the source evidence trail below."

                # 2. Obvious Answer Separator
                console.print("\n" + "========== FINAL SCHOLARLY RESPONSE ==========")
                
                # 3. Render Answer with Markdown Support
                console.print(Panel(
                    Markdown(answer),
                    border_style="vaidya",
                    padding=(1, 2),
                    box=ROUNDED,
                    title="[bold vaidya] Scholarly Synthesis [/]"
                ))
                
                # 3. Restore Raw Source Data (The Evidence Trail)
                if results:
                    console.print("\n" + "========== PRIMARY SOURCE EVIDENCE TRAIL ==========")
                    for i, (doc_id, score) in enumerate(results):
                        payload = retriever.search_engine.id_to_payload.get(doc_id)
                        if not payload: continue
                        
                        treatise = payload.get('source_treatise', 'Unknown')
                        
                        # Graph Context Breadcrumb
                        ctx = retriever.context_manager.expand_context(doc_id, payload)
                        breadcrumb = " > ".join([b["title"] for b in ctx["breadcrumb"]])
                        
                        # Structured evidence panel
                        evidence_content = (
                            f"[bold info]PATH:[/] {treatise} > {breadcrumb}\n"
                            f"[bold info]SCORE:[/] {score:.4f}  [bold info]ID:[/] [dim]{doc_id}[/]\n"
                            f"[rule dim]\n"
                            f"{payload.get('content', '')}"
                        )

                        console.print(Panel(
                            evidence_content,
                            title=f"[bold source]SOURCE {i+1}[/]",
                            border_style="source",
                            padding=(1, 2)
                        ))
                
                console.print("="*50 + "\n")
                        
            except Exception as e:
                console.print(f"\n[bold error][!!!] ERROR: {e}[/]")
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/]")

if __name__ == "__main__":
    main()
