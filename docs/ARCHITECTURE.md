# Architecture

## System Diagram

```
+====================================================================+
|                   INGESTION PIPELINE                                |
|   Neo4j Ingest -> Parser -> Enricher -> Linker -> Embedder -> DB    |
+====================================================================+
                                                                       
  +------------+    +----------------+    +-------------------+        
  | Knowledge  |    | Individual     |    | CrossLinker       |        
  | Graph CSVs |--->| Workers        |--->| (Semantic Logic)  |        
  | (Neo4j)    |    | (Phase 1-3)    |    | - shared terms    |        
  +-----+------+    +-------+--------+    | - neo4j_entities  |        
        |                   |             +---------+---------+        
        v                   |                       |                  
  +------------+   +---------v---------+   +---------v---------+        
  | Neo4j DB   |   | RemoteEmbedder    |   | AyurvedaUploader  |        
  | (Graph)    |   | (GPU Sidecar)     |   | (Phase 5)         |        
  +------------+   | - encode()        |<--| - batch processing|        
                   | - encode_sparse() |   | - multi-vector    |        
                   | - rerank()        |   +---------+---------+        
                   +---------+---------+             |                  
                             |             +---------v---------+        
                             |             | Qdrant Vector DB  |        
                             |             | Collection:       |        
                             |             | ayurveda_rag      |        
                             +------------>| Named Vectors:     |        
                                           |  - dense_english   |        
                                           |  - dense_sanskrit  |        
                                           |  - sparse_splade   |        
                                           +--------------------+        

+====================================================================+
|                 KNOWLEDGE DISCOVERY LAYER                           |
|      Vector DB  ->  Graph Engine  ->  Analytical UI                 |
+====================================================================+

  +------------------+    +--------------------+    +------------------+
  | Qdrant Points    |--->| NetworkX Engine    |--->| Sigma.js WebGL   |
  | (ayurveda_rag)   |    | - Centrality       |    | - Thematic View  |
  +------------------+    | - Louvain Clusters |    | - Hub Highlights |
                          +--------------------+    +------------------+

+====================================================================+
|                     QUERY PIPELINE                                  |
|   User Input -> Router -> Agent -> Graph (Siddhanta) -> Vector (Pramana) -> Handshake -> Synthesis |
+====================================================================+

  +----------+     +------------------+     +------------------+       
  | User CLI |---->| AyurvedaRouter   |---->| AyurvedaRetriever|
  | (rich)   |     | (Pre-Retrieval)  |     | (Vaidya Agent)   |
  +----------+     | - Entity Detection|     | - Gemini 2.5-fl  |
                   | - Direct Citation|     | - Tool Decomp    |
                   | - Sanskrit Terms |     | - Handshake Logic|
                   +---------+--------+     +---------+--------+               
                             |              |         |        |
                             |      +-------v-------+ | +------v-------+
                             |      | Neo4jGraphTool| | | AyurvedaSearchEng
                             |      | (Siddhanta)   | | | (Pramana)      |
                             |      +-------+-------+ | +------+-------+
                             v              |         |        |
                   +------------------+     +---------+--------+
                   | Metadata Bridge  |<----+ (neo4j_entities) |
                   | (Handshake)      |     |                  |
                   +---------+--------+     +------------------+
                             |                                         
                   +---------v--------+                                 
                   | Gemini LLM       |                                 
                   | (Synthesis)      |                                 
                   | -> Siddhanta-    |
                   |    Pramana Samyoga|
                   +------------------+                                 
```

## Unified Scholarly Workflow (The Handshake)

The system enforces a 4-phase reasoning chain to ensure clinical rigor:

1. **Phase A: Siddhanta (Graph)**: If a Disease, Plant, or Formulation is detected, the Agent MUST call `query_knowledge_graph` first to establish canonical facts and IDs.
2. **Phase B: Pramana (Vector)**: The Agent uses canonical terms from the Graph to perform high-precision searches in Qdrant.
3. **Phase C: Metadata Handshake**: The Agent cross-references `metadata.neo4j_entities` in vector hits with the Graph IDs. Only matching hits are treated as "Primary Evidence."
4. **Phase D: Relational Hopping**: Relationship types (e.g., `INGREDIENT_OF`) trigger recursive vector searches for newly discovered entities.

+====================================================================+
|                    EXTERNAL SERVICES                                 |
+====================================================================+
                                                                       
  +------------------+    +--------------------+    +------------------+
  | Qdrant (host)    |    | GPU Sidecar        |    | Neo4j (host)     |
  | Port: 6333       |    | Port: 8080         |    | Port: 7474/7687  |
  | Docker container |    | Docker container   |    | Docker container |
  | qdrant/qdrant    |    | nvidia/pytorch     |    | neo4j:5.12       |
  +------------------+    +--------------------+    +------------------+
                           | Models loaded:        | Plugins:         |
                           |  - multilingual-e5    |  - APOC          |
                           |  - bge-reranker       +------------------+
                           |  - splade-v3          |
                           +--------------------+                       
```

## Communication Patterns

| Component Pair | Pattern | Details |
|----------------|---------|---------|
| Parser -> Database | Function call | `upload_book(book_dir)` via `AyurvedaUploader` |
| Python -> Qdrant | HTTP/gRPC SDK | `qdrant_client` Python SDK on localhost:6333 |
| Python -> GPU Sidecar | HTTP REST | `requests` POST with `tenacity` exponential backoff |
| Agent -> LLM | SDK | `google.genai` SDK with function-calling tools |
| Agent -> Search Engine | Function call | `self.search_engine.search()` |
| Router -> Search Engine| Function/Param | Router outputs parameters used by Agent tools |

## Ingestion Pipeline (End-to-End)

1. Raw text loaded from `books/<treatise>/` (JSON or Markdown).
2. Samhita-specific parser traverses structure.
3. Parser outputs a list of chunk dicts.
4. `AyurvedaUploader.upload_book()`:
   - Calls `RemoteEmbedder.encode()` for `dense_english` vector.
   - Calls `RemoteEmbedder.encode()` on normalized text for `dense_sanskrit` vector.
   - Calls `RemoteEmbedder.encode_sparse()` for `sparse_splade` vector.
   - Upserts to Qdrant collection `ayurveda_rag` in batches of 32.

## Query Pipeline (End-to-End)

1. User enters natural-language query in CLI (`src/retriever/main.py`).
2. `AyurvedaRouter` classifies the query (LLM intent extraction, direct citation parsing, technical term extraction).
3. `AyurvedaRetriever.generate_answer()` creates a Gemini chat session with three tools, passing the routing advice.
4. Gemini agentic loop calls tools as needed.
5. `search_treatises` calls `AyurvedaSearchEngine.hybrid_search()`.
6. `hybrid_search` embeds query using E5, normalizes for Sanskrit, gets SPLADE sparse vector, runs 3 parallel prefetches, fuses with RRF, reranks with BGE cross-encoder.
7. Results are filtered and returned to agent.
8. Agent may call `get_verse_context` for contiguous verses or `lookup_glossary` for term resolution.
9. Agent synthesizes final answer in Siddhanta format.