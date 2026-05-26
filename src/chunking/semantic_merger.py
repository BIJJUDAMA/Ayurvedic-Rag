import os
import numpy as np
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from src.chunking.remote_embedder import RemoteEmbedder

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AccordionMerger")
console = Console()

class AyurvedaAccordion:
    """
    CONSOLIDATION ENGINE: Merges semantically redundant chunks (>0.95 similarity).
    This fixes the 'STIFF' boundary problem and frees up retrieval slots.
    """
    def __init__(self, collection_name: str = "ayurveda_rag"):
        self.client = QdrantClient(host="localhost", port=6333)
        self.collection_name = collection_name
        self.model = RemoteEmbedder()
        self.merge_threshold = 0.95
        self.max_merged_length = 2000 # Safety cap

    def run_dry_run(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Identifies all merge candidates without modifying the database."""
        console.print(f"\n[bold yellow]Initiating Accordion Scan for '{self.collection_name}'...[/]\n")
        
        res, _ = self.client.scroll(
            collection_name=self.collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=True
        )

        candidates = []
        for point in res:
            next_id = point.payload.get("next_id")
            if not next_id: continue

            neighbor = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[next_id],
                with_vectors=True
            )
            if not neighbor: continue
            
            # Calculate Similarity
            v1 = point.vector.get("dense_english")
            v2 = neighbor[0].vector.get("dense_english")
            
            if v1 and v2:
                sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
                if sim > self.merge_threshold:
                    combined_len = len(point.payload.get("content", "")) + len(neighbor[0].payload.get("content", ""))
                    if combined_len < self.max_merged_length:
                        candidates.append({
                            "source_id": point.id,
                            "target_id": next_id,
                            "similarity": sim,
                            "treatise": point.payload.get("source_treatise"),
                            "level": point.payload.get("level")
                        })
        
        console.print(f"[green]Found {len(candidates)} merge candidates.[/]")
        return candidates

    def merge_and_upsert(self, candidates: List[Dict[str, Any]]):
        """
        Executes the merge:
        1. Combines text and metadata.
        2. Regenerates vectors for the new consolidated chunk.
        3. Relinks parent-child relationships for orphaned nodes.
        4. Upserts the new node and deletes the redundant target.
        """
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Merging Chunks...", total=len(candidates))

            for c in candidates:
                # 1. Retrieve full data for both
                points = self.client.retrieve(
                    collection_name=self.collection_name,
                    ids=[c["source_id"], c["target_id"]],
                    with_payload=True
                )
                if len(points) < 2: 
                    progress.advance(task)
                    continue
                
                p1, p2 = (points[0], points[1]) if points[0].id == c["source_id"] else (points[1], points[0])
                
                # 2. Build Merged Payload
                merged_content = f"{p1.payload['content']}\n\n{p2.payload['content']}"
                merged_payload = p1.payload.copy()
                merged_payload["content"] = merged_content
                merged_payload["next_id"] = p2.payload.get("next_id")
                merged_payload["accordion_merged"] = True
                
                # Update verse_ref if applicable (e.g., "1" + "2" -> "1-2")
                v1 = str(p1.payload.get("verse_ref", ""))
                v2 = str(p2.payload.get("verse_ref", ""))
                if v1 and v2 and v1 != v2:
                    merged_payload["verse_ref"] = f"{v1}-{v2}"

                # 3. Regenerate Vectors (Mandatory for accuracy)
                # Dense English
                v_eng = self.model.encode(f"passage: {merged_content}").tolist()
                
                # Dense Sanskrit (Extracting Sanskrit from both if present)
                v_san = self.model.encode(f"passage: {merged_content}").tolist()
                
                # Sparse SPLADE
                sparse_dict = self.model.encode_sparse(merged_content)
                v_sparse = models.SparseVector(
                    indices=[int(k) for k in sparse_dict.keys()], 
                    values=[float(v) for v in sparse_dict.values()]
                )

                # 4. Relink Children of the deleted node (Maintain Tree Integrity)
                children, _ = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=models.Filter(
                        must=[models.FieldCondition(key="parent_id", match=models.MatchValue(value=str(p2.id)))]
                    ),
                    with_payload=True
                )
                for child in children:
                    child.payload["parent_id"] = str(p1.id)
                    self.client.overwrite_payload(
                        collection_name=self.collection_name,
                        payload=child.payload,
                        points=[child.id]
                    )

                # 5. Atomic Upsert & Delete
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=[
                        models.PointStruct(
                            id=p1.id,
                            vector={
                                "dense_english": v_eng,
                                "dense_sanskrit": v_san,
                                "sparse_splade": v_sparse
                            },
                            payload=merged_payload
                        )
                    ]
                )
                
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=models.PointIdsList(points=[p2.id])
                )

                progress.advance(task)

if __name__ == "__main__":
    accordion = AyurvedaAccordion()
    candidates = accordion.run_dry_run()
    
    if candidates:
        console.print(f"\n[bold red]WARNING: Found {len(candidates)} redundant boundaries.[/]")
        console.print("[bold red]Proceeding will permanently merge these nodes in the production database.[/]")
        
        try:
            confirm = input("\nDo you want to execute the merge now? (y/N): ").strip().lower()
            if confirm == 'y':
                accordion.merge_and_upsert(candidates)
                console.print("\n[bold green]✔ Semantic consolidation complete.[/]")
            else:
                console.print("\n[yellow]Merge cancelled. No changes made.[/]")
        except EOFError:
            console.print("\n[yellow]Non-interactive environment detected. Skipping merge.[/]")
    else:
        console.print("\n[bold green]✔ No redundant boundaries detected. Your database is already optimized.[/]")
