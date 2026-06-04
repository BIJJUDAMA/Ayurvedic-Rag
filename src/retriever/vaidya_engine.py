import os
import json
from typing import List, Dict, Any, Optional, Tuple
from qdrant_client import QdrantClient
from qdrant_client.http import models
from google import genai
from google.genai import types
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.box import DOUBLE
from src.chunking.remote_embedder import RemoteEmbedder
from src.retriever.search_engine import AyurvedaSearchEngine
from src.retriever.context_manager import AyurvedaContextManager
from src.retriever.router import AyurvedaRouter
from src.retriever.graph_tool import Neo4jGraphTool

# Global console for logging (can be overridden)
_console = Console()

class AyurvedaRetriever:
    """
    Ayurveda RAG: Production-grade Agentic Retrieval and Synthesis.
    Optimized for multi-vector hybrid search across classical Samhitas using GPU Sidecar.
    """
    def __init__(self, 
                 collection_name: str = "ayurveda_rag", 
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 console: Optional[Console] = None):
        
        self.collection_name = collection_name
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.console = console or _console
        
        # Verify Qdrant connection early
        try:
            self.client.get_collections()
        except Exception as e:
            self.console.print(f"[bold error][!] Connection Error:[/] Could not connect to Qdrant at {qdrant_host}:{qdrant_port}.")
            self.console.print("[info][*] Tip: Ensure Docker Desktop is running and run 'docker-compose up -d'.[/]")
            raise RuntimeError(f"Qdrant unreachable: {e}")

        # Session state for tracking hits across tool calls
        self.session_hits = {} # doc_id -> {score, title, text, source}
        
        # Load Remote Embedding Model (GPU Sidecar)
        self.console.print("[info]Connecting to GPU Inference Sidecar...[/]")
        self.model = RemoteEmbedder()
        if not self.model.is_available():
            self.console.print("[bold red][!] Error:[/] GPU Sidecar not reachable at http://localhost:8080")
            raise RuntimeError("GPU Sidecar unreachable. Run 'docker-compose up -d' first.")
        
        # Gemini Client
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            self.llm_client = genai.Client(
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
        else:
            print("Warning: GOOGLE_API_KEY not found in .env. LLM generation disabled.")
            self.llm_client = None

        # Sub-components
        self.search_engine = AyurvedaSearchEngine(self.client, collection_name, self.model)
        self.context_manager = AyurvedaContextManager(self.client, collection_name)
        self.router = AyurvedaRouter(self.llm_client)
        self.graph_tool = Neo4jGraphTool(console=self.console)


    # --- Tool Definitions with Verbose & Strict Instructions ---

    def search_treatises(self, query: str, intent: Optional[str] = None, treatise: Optional[str] = None, sanskrit_term: Optional[str] = None) -> str:
        """
        MANDATORY PRIMARY SEARCH TOOL:
        Executes a high-precision hybrid semantic (dense) and keyword (sparse) search across the Ayurveda knowledge graph.
        
        STRICT OPERATIONAL USAGE:
        - This is your primary instrument for locating specific verses (Sutras) or therapeutic guidance.
        
        INTENT SELECTION RULE:
        - 'Sutra'    → query is about a principle, definition, or general law.
        - 'Nidana'   → query is about causation, pathogenesis, or risk factors.
        - 'Sharira'  → query is about anatomy, physiology, or tissue-level mechanisms.
        - 'Chikitsa' → query is about treatment, formulation, or therapeutic procedure.
        *The 'intent' parameter performs server-side filtering directly on database metadata. ALWAYS use it when the intent is clear.*

        HIGH RECALL OPTIMIZATION:
        - If you have a Sanskrit technical term (e.g., 'srotas', 'jvara'), provide it in the 'sanskrit_term' parameter.
        - The engine will automatically perform multi-query fusion (English + Sanskrit + Intent-Boost) to find the best match.

        - query: The conceptual search string (English or Sanskrit).
        - intent: Use the intent selection rules above.
        - treatise: Optional filter for 'charak_samhita', 'shusrut_samhita', or 'astanga_hridaya'.
        - sanskrit_term: Optional technical Sanskrit term to expand the search.
        """
        self.console.print("\n" + "="*30)
        self.console.print(Panel(
            Text.assemble(
                ("TOOL CALL: ", "bold cyan"),
                ("search_treatises", "bold yellow"),
                ("\nQUERY: ", "bold"), query,
                ("\nSANSKRIT: ", "bold"), str(sanskrit_term),
                ("\nINTENT: ", "bold"), str(intent),
                ("\nTREATISE: ", "bold"), str(treatise)
            ),
            title="[bold blue]MANUSCRIPT DISCOVERY[/]",
            border_style="cyan",
            box=DOUBLE
        ))

        # Use current session's routing info if available
        citation_params = getattr(self, 'current_route', {}).get('citation_params')

        results = self.search_engine.search(
            original_query=query,
            expanded_queries=[sanskrit_term] if sanskrit_term else None,
            top_n=7, # Reduced from 15 to prevent context overwhelming/empty responses
            intent_filter=intent,
            treatise_filter=treatise,
            citation_params=citation_params,
            original_user_query=getattr(self, 'current_user_query', None)
        )
        
        formatted_results = []
        terminal_summary = []
        for res in results:
            doc_id = res["id"]
            score = res["score"]
            payload = res.get("metadata") or self.client.retrieve(self.collection_name, [doc_id])[0].payload
            
            # Expand context natively
            ctx = self.context_manager.expand_context(doc_id, payload)
            breadcrumb = " > ".join([str(b.get("title") or "Untitled") for b in ctx["breadcrumb"]])
            
            # Stitch preceding, target, and succeeding verses together
            prev_texts = " ".join([p.get("content", "") for p in ctx["neighbors"]["prev"]])
            next_texts = " ".join([n.get("content", "") for n in ctx["neighbors"]["next"]])
            full_context = f"{prev_texts} {payload.get('content')} {next_texts}".strip()

            # Track expanded context for Ragas Evaluation & Agent Synthesis
            if doc_id not in self.session_hits or score > self.session_hits[doc_id]["score"]:
                res_copy = res.copy()
                res_copy["text"] = full_context  # Overwrite short text with full block
                res_copy["metadata"] = payload # Ensure metadata is present
                self.session_hits[doc_id] = res_copy
            
            res_str = f"SOURCE_ID: {doc_id}\n"
            res_str += f"RELEVANCE_SCORE: {score:.2f}\n"
            res_str += f"HIERARCHICAL_PATH: {payload.get('source')} > {breadcrumb}\n"
            res_str += f"EXPANDED_CONTEXT: {full_context}\n"
            res_str += "-" * 20 + "\n"
            formatted_results.append(res_str)
            
            # For terminal visualization
            terminal_summary.append(f"[bold gold3]{payload.get('source')}[/]: {payload.get('content')[:150]}...")

        if terminal_summary:
            self.console.print(Panel(
                "\n".join(terminal_summary),
                title="[bold green]RETRIEVED EVIDENCE[/]",
                border_style="green"
            ))
        else:
            self.console.print("[bold red]No matches found in the Samhitas.[/]")
            
        self.console.print("="*30 + "\n")
            
        return "\n".join(formatted_results) if formatted_results else "NO_RESULTS_FOUND: The current search parameters yielded no matches in the Samhitas."

    def get_verse_context(self, verse_id: str) -> str:
        """
        SEQUENTIAL INTEGRITY & CONTEXTUAL EXPANSION TOOL:
        Retrieves the exact preceding and succeeding verses, as well as the full hierarchical breadcrumb for a specific ID.
        
        STRICT USAGE RULE:
        1. MANDATORY TRIGGER: Call this tool if a search result contains pronouns, references to 'this', or if the meaning is aphoristic (Sutra).
        2. VERSE RANGE TRIGGER: ALSO CALL this tool when the verse reference is a range spanning more than 2 verses (e.g., [11-14]), as multi-verse blocks frequently assume context from the preceding verse block.
        3. CALL LIMIT: Call this tool a maximum of two times per query. If after two context retrievals the Adhikarana is still unclear, state this in LIMITATIONS.
        
        USAGE INSTRUCTION:
        Once context is retrieved: use the preceding verse to identify the Adhikarana (grammatical and logical subject). 
        Integrate this into your answer silently — do not quote the neighboring verses unless they are independently significant. 
        Cite them as context only if they change the meaning of the primary verse.
        """
        self.console.print("\n" + "="*30)
        self.console.print(Panel(
            Text.assemble(
                ("TOOL CALL: ", "bold cyan"),
                ("get_verse_context", "bold yellow"),
                ("\nVERSE_ID: ", "bold"), verse_id
            ),
            title="[bold blue]GRAPH TRAVERSAL[/]",
            border_style="cyan",
            box=DOUBLE
        ))

        try:
            res = self.client.retrieve(collection_name=self.collection_name, ids=[verse_id])
            if not res: return "ERROR: Verse ID not found in database."
            payload = res[0].payload
        except: return "ERROR: Invalid Verse ID."
        
        ctx = self.context_manager.expand_context(verse_id, payload)
        breadcrumb = " > ".join([str(b.get("title") or "Untitled") for b in ctx["breadcrumb"]])
        
        context_str = f"PATHWAY: {payload.get('source')} > {breadcrumb}\n"
        context_str += "SEQUENTIAL_CHAIN:\n"
        for p in ctx["neighbors"]["prev"]:
            context_str += f"  [PRECEDING_VERSE]: {p.get('content')}\n"
        context_str += f"  ► [TARGET_VERSE]: {payload.get('content')}\n"
        for n in ctx["neighbors"]["next"]:
            context_str += f"  [SUCCEEDING_VERSE]: {n.get('content')}\n"

        self.console.print(Panel(
            f"[bold blue]PATH:[/]: {breadcrumb}\n[bold blue]SUBJECT:[/]: {payload.get('content')[:150]}...",
            title="[bold green]CONTEXT LOADED[/]",
            border_style="green"
        ))
        self.console.print("="*30 + "\n")
            
        return context_str

    def lookup_glossary(self, term: str) -> str:
        """
        GLOSSARY & BOTANICAL LOOKUP TOOL:
        Retrieves canonical definitions for Sanskrit technical terms (Paribhasha) or botanical identifiers (Dravyaguna).
        
        STRICT USAGE RULE:
        - ONLY use this for Sanskrit terms (e.g., 'Pitta', 'Srotas', 'Ojas') or specific Ayurvedic concepts.
        - DO NOT use this for broad English words like 'health', 'fever', 'diet', or 'treatment'.
        - If a term is English, skip this tool and use 'search_treatises' directly.
        """
        self.console.print("\n" + "="*30)
        self.console.print(Panel(
            Text.assemble(
                ("TOOL CALL: ", "bold cyan"),
                ("lookup_glossary", "bold yellow"),
                ("\nTERM: ", "bold"), term
            ),
            title="[bold blue]LINGUISTIC ANALYSIS[/]",
            border_style="cyan",
            box=DOUBLE
        ))

        # E5 Prefix requirement: "query: " for retrieval
        query_prefix = "query: "

        # Hybrid Glossary Lookup
        # 1. Vectors
        dense_eng = self.model.encode(f"{query_prefix}{term}").tolist()
        sparse_dict = self.model.encode_sparse(term)
        sparse_vec = models.SparseVector(
            indices=[int(k) for k in sparse_dict.keys()],
            values=[float(v) for v in sparse_dict.values()]
        )

        # 2. Query with RRF and Filter
        hits = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=dense_eng,
                    using="dense_english",
                    limit=10,
                    filter=models.Filter(should=[
                        models.FieldCondition(key="level", match=models.MatchValue(value="stub_glossary")),
                        models.FieldCondition(key="level", match=models.MatchValue(value="stub_botanical"))
                    ])
                ),
                models.Prefetch(
                    query=dense_eng,
                    using="dense_sanskrit",
                    limit=10,
                    filter=models.Filter(should=[
                        models.FieldCondition(key="level", match=models.MatchValue(value="stub_glossary")),
                        models.FieldCondition(key="level", match=models.MatchValue(value="stub_botanical"))
                    ])
                ),
                models.Prefetch(
                    query=sparse_vec,
                    using="sparse_splade",
                    limit=10,
                    filter=models.Filter(should=[
                        models.FieldCondition(key="level", match=models.MatchValue(value="stub_glossary")),
                        models.FieldCondition(key="level", match=models.MatchValue(value="stub_botanical"))
                    ])
                )
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=5
        )
        
        results = []
        terminal_defs = []
        for hit in hits.points:
            title = hit.payload.get('title') or hit.payload.get('section_title') or "Untitled Glossary Entry"
            content = hit.payload.get('content') or "No content available."
            results.append(f"TERM_ENTRY: {title}\nDEFINITION: {content}")
            terminal_defs.append(f"[bold cyan]{title}[/]: {content[:200]}...")
            
        if terminal_defs:
            self.console.print(Panel(
                "\n".join(terminal_defs),
                title="[bold green]GLOSSARY MAPPINGS[/]",
                border_style="green"
            ))
        else:
            self.console.print("[bold red]Term not found in canonical glossary.[/]")

        self.console.print("="*30 + "\n")

        return "\n".join(results) if results else f"TERM_NOT_FOUND: '{term}' is not present in the canonical glossary."

    def generate_answer(self, query: str):
        """Agentic RAG Pipeline with Comprehensive Scholarly Mandate."""
        if not self.llm_client:
            return [], "LLM not configured."

        # Reset session hits for new query
        self.session_hits = {}
        self.current_user_query = query

        # 1. Route Query to get scholarly advice
        self.current_route = self.router.route(query)
        route_info = self.current_route
        self.console.print(f"[bold magenta][Router][/] Mode: {route_info['mode']} | Intent: {route_info['intent']} | Lang: {route_info['language']}")
        
        # 2. Construct Dynamic Routing Advice
        routing_advice = f"\nSCHOLAR'S ROUTING ADVICE:\n{route_info['hints']}\n"
        if route_info['mode'] == "DIRECT":
            routing_advice += "[STRICT] DIRECT CITATION DETECTED. You MUST prioritize finding and quoting the exact verse specified above.\n"

        tools = [
            self.search_treatises, 
            self.get_verse_context, 
            self.lookup_glossary,
            self.graph_tool.query_knowledge_graph
        ]
        
        system_instruction = f"""
        ROLE:
        You are Vaidya — a senior Ayurvedic scholar. Your task is to perform 'SIDDHANTA' (Canonical Conclusion).
        You provide high-precision answers strictly grounded in classical Samhitas by bridging clinical facts (Siddhanta) with textual evidence (Pramana).

        {routing_advice}

        UNIFIED SCHOLARLY WORKFLOW (Graph-Vector Handshake):
        1. PHASE A: SIDDHANTA (Graph Tool)
           - If a clinical entity (Disease/Plant/Formulation) is detected, you MUST call 'query_knowledge_graph' FIRST.
           - This establishes the "Siddhanta" (Canonical Fact). Identify the precise ID (e.g., PLANT-042).
        2. PHASE B: PRAMANA (Vector Store)
           - Use the canonical names and relational facts from the Graph to formulate a high-precision 'search_treatises' query.
           - You will receive mixed results: Evidence Chunks (Verses) and Anchor Chunks (Stubs).
        3. PHASE C: METADATA HANDSHAKE & NOISE SEPARATION
           - Inspect 'metadata.neo4j_entities' in the returned verses.
           - SIGNAL: If the verse contains the matching Neo4j ID, it is 100% Clinical Evidence.
           - NOISE: If a verse mentions a term but lacks the matching ID, it is a "Linguistic Mention" (Noise).
           - STUB ANCHOR: If you retrieve a 'stub_glossary', use it as a Definition Anchor, not as proof. Use it to extract the canonical name to re-weight other verse chunks.
        4. PHASE D: GRAPH HOPPING (Relational Traversal)
           - If a verse mentions a new term or relationship not in your initial lookup, "hop" back to the 'graph_tool' to verify the new relationship.
           - Voluntarily initiate a second 'search_treatises' call if a new formulation is discovered via the graph.

        SCHOLARLY OUTPUT PROTOCOL:
        - STRUCTURAL TEMPLATE:
          - If a 'stub_glossary' is found, the final answer MUST begin with the Canonical Definition from that stub as a Heading.
          - SIDDHANTA: Summarize the validated relationships (Dosage, Ingredients, Targets) from the Graph.
          - PRAMANA: Quote the original Sanskrit and English translation from matching verses (The Body).
        - GRAPH-VERSE COHESION (Validator):
          - If Neo4j claims a relationship that the retrieved verses do not mention, explicitly flag this as a "Textual Gap."
        - VALIDATION: State: "Siddhanta (Neo4j) confirms this treatment, and Pramana (Qdrant Verse ID: [X]) provides the textual authority."
        """

        chat = self.llm_client.chats.create(
            model=self.model_id,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools
            )
        )

        try:
            response = chat.send_message(query)
            answer_text = response.text
            if not answer_text:
                # Check for safety ratings or blocked content if text is empty
                if hasattr(response, 'candidates') and response.candidates:
                    finish_reason = response.candidates[0].finish_reason
                    answer_text = f"The scholarly engine stopped without generating text. (Reason: {finish_reason})"
                else:
                    answer_text = "The scholarly engine returned an empty response. This may be due to safety filters or model unavailability."
        except Exception as e:
            answer_text = f"An error occurred during scholarly synthesis: {str(e)}"
        
        # Sort session hits by score for return
        sorted_hits = sorted(self.session_hits.items(), key=lambda x: x[1]['score'], reverse=True)
        
        return sorted_hits, answer_text
