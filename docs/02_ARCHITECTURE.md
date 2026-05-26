# Architecture

## System Diagram

```
+====================================================================+
|                   INGESTION PIPELINE                                |
|   Raw Source  ->  Parser  ->  Enricher  ->  Embedder  ->  DB        |
+====================================================================+
                                                                       
  +------------+    +----------------+    +-------------------+        
  | Samhita    |--->| Individual     |    | CrossLinker       |        
  | Sources    |    | Workers        |--->| (Semantic Logic)  |        
  | (JSON/MD)  |    | (Phase 1-3)    |    | - shared terms    |        
  +------------+    +-------+--------+    | - related_nodes   |        
                            |             +---------+---------+        
                            |                       |                  
                  +---------v---------+   +---------v---------+        
                  | RemoteEmbedder    |   | AyurvedaUploader  |        
                  | (GPU Sidecar)     |   | (Phase 5)         |        
                  | - encode()        |<--| - batch processing|        
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
|   User Input -> Router -> Agent -> Search -> Rerank -> Synthesis    |
+====================================================================+

  +----------+     +------------------+     +------------------+       
  | User CLI |---->| AyurvedaRouter   |---->| AyurvedaRetriever|
  | (rich)   |     | (Pre-Retrieval)  |     | (Vaidya Agent)   |
  +----------+     | - LLM Intent     |     | - Gemini 2.5-fl  |
                   | - Direct Citation|     | - Tools:         |       
                   | - Technical Terms|     |   search_treatises|    
                   +---------+--------+     |   get_verse_context|   
                             |              |   lookup_glossary |               
                             v              +---------+--------+               
                   +------------------+               |                
                   | AyurvedaSearchEng|<--------------+                
                   | hybrid_search()  |                                 
                   | - 3 prefetches   |                                 
                   | - RRF fusion     |                                 
                   | - rerank (BGE)   |                                 
                   +---------+--------+                                 
                             |                                         
                   +---------v--------+                                 
                   | Gemini LLM       |                                 
                   | (Synthesis)      |                                 
                   | -> Siddhanta     |                                 
                   +------------------+                                 

+====================================================================+
|                    EXTERNAL SERVICES                                 |
+====================================================================+
                                                                       
  +------------------+    +--------------------+                       
  | Qdrant (host)    |    | GPU Sidecar        |                       
  | Port: 6333       |    | Port: 8080         |                       
  | Docker container |    | Docker container   |                       
  | qdrant/qdrant    |    | nvidia/pytorch:24.10|                      
  +------------------+    +--------------------+                       
                           | Models loaded:                           
                           |  - multilingual-e5-large                  
                           |  - bge-reranker-base                     
                           |  - splade-v3                             
                           +--------------------+                       
                                                                       
  +------------------+                                                
  | Google Gemini API|                                                
  | gemini-2.5-flash-|                                                
  | lite             |                                                
  | Via google-genai |                                                
  +------------------+                                                
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