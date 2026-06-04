import os
import json
import random
import re
import time
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from google import genai
from google.genai import types
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from dotenv import load_dotenv

from src.chunking.remote_embedder import RemoteEmbedder

# Load env vars
load_dotenv()

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "ayurveda_rag"
OUTPUT_PATH = os.path.join("src", "evaluation", "dataset.json")

# Mapping internal Samhita names to actual 'source' field values in Qdrant
TREATISE_MAP = {
    "Charaka": ["charak_samhita"],
    "Susruta": ["shusrut_samhita"],
    "Astanga": ["astanga_hridaya"]
}

STRATEGIES = [
    "CLINICAL_CASE",      # Scenario-based multi-hop reasoning
    "SYNONYM_TRAP",       # Forbidden from using text keywords
    "CROSS_REFERENCE",    # Requires reading two related chunks
    "IMPERFECT_SCHOLAR",  # Phonetic spelling and rambling
    "ADVERSARIAL"         # Conceptual distraction/Rejection testing
]

console = Console()

class SyntheticDatasetGenerator:
    """
    LLM-POWERED DATASET GENERATOR (Gemini-2.0-Flash-Lite).
    Constructs a ground truth dataset by asking Gemini to generate realistic 
    scholarly queries based on actual manuscript chunks.
    """
    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in .env file.")
        
        self.genai_client = genai.Client(api_key=api_key)
        self.model_id = 'gemini-2.5-flash-lite'
        self.embedder = RemoteEmbedder()

    def fetch_sample_chunks(self, source_values: List[str], limit: int = 25) -> List[Any]:
        """Fetch random verse or section-level chunks for LLM processing."""
        res, _ = self.client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="source", match=models.MatchAny(any=source_values)),
                    models.FieldCondition(key="level", match=models.MatchAny(any=["verse", "verse_block", "section", "chapter"]))
                ]
            ),
            limit=500, 
            with_payload=True,
            with_vectors=False
        )

        if not res:
            console.print(f"[red]No chunks found for {source_values}[/]")
            return []

        # Filter for chunks with enough context for a question
        valid_chunks = [c for c in res if len(c.payload.get("content", "")) > 150] # Increased min length for better context
        if not valid_chunks: valid_chunks = res

        random.shuffle(valid_chunks)
        return valid_chunks[:limit]

    def find_related_chunk(self, original_chunk_id: str, content: str, exclude_treatises: List[str]) -> Optional[Dict]:
        """Finds a semantically similar chunk in a different treatise for comparative queries."""
        try:
            # E5 Prefix requirement: "query: "
            vector = self.embedder.encode(f"query: {content}")
            
            hits = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                using="dense_english",
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="source", match=models.MatchAny(any=exclude_treatises)),
                        models.FieldCondition(key="level", match=models.MatchAny(any=["verse", "verse_block", "section"]))
                    ],
                    must_not=[
                        models.HasIdCondition(has_id=[original_chunk_id])
                    ]
                ),
                limit=1
            )
            
            if hits.points:
                return {
                    "id": str(hits.points[0].id),
                    "content": hits.points[0].payload.get("content", ""),
                    "treatise": hits.points[0].payload.get("source")
                }
        except Exception as e:
            console.print(f"[red]Error finding related chunk: {e}[/]")
        return None

    def generate_query_via_llm(self, chunk_content: str, samhita: str, strategy: str, secondary_chunk: Optional[Dict] = None, max_retries: int = 5) -> Optional[str]:
        """Asks Gemini to generate a realistic scholarly query based on a specific strategy."""
        
        base_context = f"PRIMARY CHUNK ({samhita}):\n{chunk_content}"
        if secondary_chunk:
            base_context += f"\n\nSECONDARY CHUNK ({secondary_chunk['treatise']}):\n{secondary_chunk['content']}"

        prompts = {
            "CLINICAL_CASE": f"""
                You are a patient describing a complex health situation. 
                Use the concepts in the provided chunk to describe a set of symptoms and lifestyle choices. 
                Ask for the underlying cause or therapeutic rationale according to the Samhita.
                DO NOT mention the text or chunk. Talk like a real person in distress.
                
                CONTEXT:
                {base_context}
            """,
            "SYNONYM_TRAP": f"""
                You are a medical researcher. Ask a specific scholarly question about the concepts in this chunk.
                CRITICAL RULE: You are FORBIDDEN from using any primary keywords or nouns found in the chunk text. 
                Use modern medical synonyms or conceptual descriptions (e.g., "metabolic efficiency" instead of "Agni").
                
                CONTEXT:
                {base_context}
            """,
            "CROSS_REFERENCE": f"""
                You are a senior Ayurvedic scholar comparing two classical texts. 
                Find the conceptual tension, missing link, or complementary detail between these two chunks.
                Ask a question that REQUIRE reading and synthesizing BOTH chunks to answer correctly.
                
                CONTEXT:
                {base_context}
            """,
            "IMPERFECT_SCHOLAR": f"""
                You are a student of Ayurveda. Ask a specific question about this chunk.
                DELIBERATE NOISE: Use non-standard phonetic spelling for Sanskrit terms (e.g., "shrootas" instead of "srotas").
                Make the query slightly vague or rambling, starting with "I read somewhere..." or "I heard that...".
                
                CONTEXT:
                {base_context}
            """,
            "ADVERSARIAL": f"""
                You are a skeptical researcher trying to find contradictions.
                Use the provided chunk (which is about a specific topic) to generate a question that sounds relevant 
                but actually asks about a different, slightly distracting concept. 
                This is a test of the system's ability to remain focused on the provided evidence.
                
                CONTEXT:
                {base_context}
            """
        }

        strategy_prompt = prompts.get(strategy, "Generate a realistic scholarly question about this chunk.")

        final_prompt = f"""
        {strategy_prompt}

        GENERAL RULES:
        1. Return ONLY the question string, nothing else.
        2. Do NOT include phrases like "Based on the text" or "According to this chunk".
        3. Ensure the question is complex and requires semantic understanding.
        """
        
        for attempt in range(max_retries):
            try:
                response = self.genai_client.models.generate_content(
                    model=self.model_id,
                    contents=final_prompt
                )
                if response and response.text:
                    return response.text.strip().strip('"')
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    wait_time = (2 ** attempt) + random.random()
                    time.sleep(wait_time)
                else:
                    break
        return None

    def run(self, samples_per_book: int = 20):
        dataset = []
        strategy_index = 0

        console.print("\n[bold gold3]─── Advanced Ayurvedic Benchmark Generation ───[/]")
        console.print(f"[dim]Strategies: {', '.join(STRATEGIES)}[/]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:

            for samhita, sources in TREATISE_MAP.items():
                task = progress.add_task(f"[cyan]Processing {samhita}...", total=samples_per_book)
                
                chunks = self.fetch_sample_chunks(sources, limit=samples_per_book)

                for chunk in chunks:
                    strategy = STRATEGIES[strategy_index % len(STRATEGIES)]
                    strategy_index += 1
                    
                    payload = chunk.payload
                    content = payload.get("content", "")
                    
                    # Handle Cross-Reference (Needs a second chunk)
                    secondary = None
                    if strategy == "CROSS_REFERENCE":
                        other_treatises = [v[0] for k, v in TREATISE_MAP.items() if k != samhita]
                        secondary = self.find_related_chunk(str(chunk.id), content, other_treatises)
                    
                    # Generate realistic query
                    query = self.generate_query_via_llm(content, samhita, strategy, secondary)
                    
                    if query:
                        entry = {
                            "query": query,
                            "expected_id": str(chunk.id),
                            "samhita": samhita,
                            "strategy": strategy,
                            "level": payload.get("level"),
                            "method": "gemini_generation",
                            "ground_truth_context": content
                        }
                        if secondary:
                            entry["secondary_expected_id"] = secondary["id"]
                        
                        dataset.append(entry)
                    
                    progress.advance(task)
                    time.sleep(0.5)

        if not dataset:
            console.print("[bold red]Failed to generate dataset.")
            return

        # Write to JSON
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)
        
        console.print(f"\n[bold green]✔ Successfully generated {len(dataset)} High-Fidelity entries.")
        console.print(f"[bold green]✔ Strategies used: {len(STRATEGIES)}")
        console.print(f"[bold green]✔ Saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    generator = SyntheticDatasetGenerator()
    # You can increase samples_per_book for a more exhaustive dataset
    generator.run(samples_per_book=25)
