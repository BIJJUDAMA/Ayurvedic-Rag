import os
import json
import random
import time
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from google import genai
from google.genai import types
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from dotenv import load_dotenv

load_dotenv()

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "ayurveda_rag"
OUTPUT_PATH = os.path.join("src", "evaluation", "dataset.json")

TREATISES = ["charak_samhita", "shusrut_samhita", "astanga_hridaya"]

console = Console()

class SyntheticDatasetGenerator:
    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment.")
        self.llm = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=8,
                    initial_delay=2.0,
                    max_delay=60.0,
                    http_status_codes=[429, 500, 502, 503, 504]
                )
            )
        )
        self.model_id = 'gemini-2.5-flash-lite'

    def fetch_sample_chunks(self, treatise: str, limit: int = 20) -> List[Any]:
        """Fetch well-spaced random chunks for a specific treatise."""
        console.print(f"[cyan]Sampling {limit} chunks from {treatise}...")

        res, _ = self.client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="source_treatise", match=models.MatchValue(value=treatise))
                ],
                should=[
                    models.FieldCondition(key="level", match=models.MatchAny(any=["section", "verse", "verse_block"]))
                ]
            ),
            limit=1000, # Higher limit to allow filtering
            with_payload=True,
            with_vectors=False
        )

        if not res:
            console.print(f"[yellow]Warning: No chunks found for {treatise} in database.")
            return []

        # Filter for meaty chunks (> 300 chars)
        meaty_chunks = [c for c in res if len(c.payload.get("content", "")) > 300]
        
        if not meaty_chunks:
            console.print(f"[yellow]Warning: No meaty chunks found for {treatise}. Falling back.")
            meaty_chunks = res

        random.shuffle(meaty_chunks)
        return meaty_chunks[:limit]

    def _resolve_title(self, payload: Dict) -> str:
        return payload.get("title") or payload.get("chapter_title") or payload.get("section_title") or "Unnamed Section"

    def _build_hierarchy(self, payload: Dict, depth: int = 3) -> List[str]:
        breadcrumb = []
        cur = payload
        for _ in range(depth):
            raw = cur.get("title") or cur.get("chapter_title") or cur.get("section_title")
            if raw:
                breadcrumb.append(raw.strip())
            pid = cur.get("parent_id")
            if not pid:
                break
            try:
                res = self.client.retrieve(collection_name=COLLECTION_NAME, ids=[pid])
                if not res:
                    break
                cur = res[0].payload
            except:
                break
        return breadcrumb

    def generate_entry(self, chunk: Any, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        payload = chunk.payload
        content = payload.get("content", "")
        title = self._resolve_title(payload)
        source = payload.get("source_treatise", "Ayurveda")
        hierarchy = self._build_hierarchy(payload)
        hierarchy_str = " > ".join(reversed(hierarchy)) if hierarchy else title

        prompt = f"""
        TASK: Create a professional RAG evaluation entry based on this Ayurvedic text.

        TEXT:
        ---
        Source: {source}
        Hierarchy: {hierarchy_str}
        Section Title: {title}
        Content: {content}
        ---

        INSTRUCTIONS:
        1. QUERY: Generate a specific, natural English query that a clinical researcher would ask to find this information.
           - STRICTION: The answer to the query MUST be present in the 'Content' block provided above.
           - DO NOT use information from the 'Hierarchy' or 'Title' if it is not in the 'Content'.
           - Use descriptive English symptoms or clinical concepts.
           - Do NOT use technical Sanskrit terms from the text (test semantic alignment).
        2. EXPECTED_ID: Use exactly '{chunk.id}'.
        3. BENCHMARK: Write a clear 1-2 sentence summary of the factual answer present ONLY in the 'Content'.

        OUTPUT JSON ONLY:
        {{
            "query": "The question",
            "expected_id": "{chunk.id}",
            "evaluation_benchmark": "The factual answer summary"
        }}
        """

        for attempt in range(max_retries):
            try:
                response = self.llm.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        response_mime_type="application/json"
                    )
                )
                return json.loads(response.text)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    console.print(f"[yellow]LLM call failed (attempt {attempt + 1}/{max_retries}), retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    console.print(f"[yellow]Skipping chunk after {max_retries} failed attempts: {e}")
                    return None

    def run(self):
        dataset = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:

            for treatise in TREATISES:
                samples_needed = 20
                task = progress.add_task(f"[cyan]Processing {treatise}...", total=samples_needed)
                chunks = self.fetch_sample_chunks(treatise, limit=samples_needed)

                count_for_treatise = 0
                for chunk in chunks:
                    entry = self.generate_entry(chunk)
                    if entry:
                        dataset.append(entry)
                        count_for_treatise += 1
                        progress.advance(task)

                if count_for_treatise < samples_needed:
                    console.print(f"[yellow]Only generated {count_for_treatise}/{samples_needed} for {treatise}")
        # Save to file
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)
        
        console.print(f"\n[bold green]✔ Synthetic dataset with {len(dataset)} items generated successfully.")
        console.print(f"[bold green]✔ Overwritten: {OUTPUT_PATH}")

if __name__ == "__main__":
    generator = SyntheticDatasetGenerator()
    generator.run()
