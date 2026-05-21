import os
from qdrant_client import QdrantClient
from rich.console import Console
from rich.panel import Panel

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "ayurveda_rag"

console = Console()
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

TARGET_ID = "3981f3cd-c950-574d-a1c8-b321db690504"

def find_chunk_and_context(chunk_id: str):
    console.print(f"[cyan]Retrieving chunk {chunk_id}...")
    
    # 1. Get the target chunk
    res = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[chunk_id],
        with_payload=True
    )
    
    if not res:
        console.print(f"[bold red]Chunk {chunk_id} not found in {COLLECTION_NAME}.")
        return

    chunk = res[0]
    payload = chunk.payload
    
    console.print(Panel(
        f"[bold cyan]Content:[/]\n{payload.get('content')}\n\n"
        f"[bold cyan]Source:[/]\n{payload.get('source_treatise')}\n"
        f"[bold cyan]Title:[/]\n{payload.get('title')}\n"
        f"[bold cyan]Level:[/]\n{payload.get('level')}\n"
        f"[bold cyan]Parent ID:[/]\n{payload.get('parent_id')}",
        title=f"Chunk: {chunk_id}"
    ))

    # 2. Find siblings (chunks with the same parent)
    parent_id = payload.get("parent_id")
    if parent_id:
        console.print(f"\n[cyan]Finding siblings for parent {parent_id}...")
        from qdrant_client.http import models
        siblings, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="parent_id", match=models.MatchValue(value=parent_id))
                ]
            ),
            limit=20,
            with_payload=True
        )
        
        for sib in siblings:
            marker = " [bold green](Target)[/]" if sib.id == chunk_id else ""
            console.print(f"- {sib.id}: {sib.payload.get('title') or 'No Title'}{marker}")
            # print first 100 chars
            snippet = (sib.payload.get('content') or "")[:100].replace("\n", " ")
            console.print(f"  [dim]{snippet}...[/]")

if __name__ == "__main__":
    find_chunk_and_context(TARGET_ID)
