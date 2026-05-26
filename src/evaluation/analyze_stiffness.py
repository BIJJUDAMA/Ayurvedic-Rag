import os
import numpy as np
from qdrant_client import QdrantClient
from rich.console import Console
from rich.table import Table

console = Console()

def analyze_stiffness(client: QdrantClient, collection: str, threshold: float = 0.95):
    """
    Identifies 'Stiff' chunk pairs where semantic similarity is too high (>0.95).
    This indicates redundant chunking boundaries that confuse the retriever.
    """
    console.print(f"\n[bold yellow]Scanning '{collection}' for Redundant/Stiff Boundaries (Sim > {threshold})...[/]\n")
    
    res, _ = client.scroll(
        collection_name=collection, 
        limit=500, 
        with_payload=True, 
        with_vectors=True
    )
    
    if not res:
        console.print("[red]No points found.")
        return

    stiff_pairs = []
    
    for point in res:
        next_id = point.payload.get("next_id")
        if not next_id: continue
        
        neighbor = client.retrieve(collection_name=collection, ids=[next_id], with_vectors=True)
        if not neighbor: continue
        
        v1 = point.vector.get("dense_english")
        v2 = neighbor[0].vector.get("dense_english")
        
        if v1 and v2:
            sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
            if sim > threshold:
                stiff_pairs.append({
                    "id1": point.id,
                    "id2": next_id,
                    "sim": sim,
                    "text1": point.payload.get("content", "")[:60],
                    "text2": neighbor[0].payload.get("content", "")[:60],
                    "treatise": point.payload.get("source_treatise")
                })

    if not stiff_pairs:
        console.print("[green]No stiff boundaries found! All chunks are semantically distinct.")
        return

    table = Table(title=f"Stiff Boundary Report (Total: {len(stiff_pairs)})")
    table.add_column("Treatise", style="dim")
    table.add_column("Sim", style="bold red")
    table.add_column("Chunk A Context", style="cyan")
    table.add_column("Chunk B Context", style="green")
    
    for p in stiff_pairs[:20]: # Show top 20
        table.add_row(
            str(p["treatise"]), 
            f"{p['sim']:.4f}", 
            p["text1"] + "...", 
            p["text2"] + "..."
        )
        
    console.print(table)
    if len(stiff_pairs) > 20:
        console.print(f"[dim]... and {len(stiff_pairs)-20} more pairs.[/]")

if __name__ == "__main__":
    client = QdrantClient("localhost", port=6333)
    analyze_stiffness(client, "ayurveda_rag")
