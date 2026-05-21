# Architecture

## System Diagram

```
+====================================================================+
|                   INGESTION PIPELINE                                |
|   Raw Source  ->  Parser  ->  Embedder  ->  Vector DB               |
+====================================================================+
                                                                       
  +------------+    +----------------+    +------------------+         
  | Charaka    |--->| CharakaParser  |    | RemoteEmbedder   |         
  | JSON files |    | +HierarchyMgr  |    | (GPU Sidecar)    |         
  +------------+    +----------------+    | - encode()       |         
                                          | - encode_sparse()|         
  +------------+    +----------------+    | - rerank()       |         
  | Susruta    |--->| parse_shusrut  |    +--------+---------+         
  | Markdown   |    | +state machine |             |                   
  +------------+    +----------------+             |                   
                                          +--------v---------+        
  +------------+    +----------------+    | unified_database  |        
  | Astanga    |--->| parse_astanga  |    | AyurvedaDatabaseMgr|        
  | Markdown   |    | +tree traversal|    | upload_chunks()   |        
  +------------+    +----------------+    +--------+---------+         
                                                   |                   
                                          +--------v---------+        
                                          | Qdrant Vector DB  |        
                                          | Collection:       |        
                                          | ayurveda_rag      |        
                                          | Named Vectors:     |        
                                          |  - dense_english   |        
                                          |  - dense_sanskrit  |        
                                          |  - sparse_splade   |        
                                          +--------------------+        

+====================================================================+
|                     QUERY PIPELINE                                  |
|   User Input  ->  Agent  ->  Search  ->  Rerank  ->  Synthesis      |
+====================================================================+

  +----------+     +------------------+     +------------------+       
  | User CLI |---->| AyurvedaRetriever|     | AyurvedaSearchEng|       
  | (rich)   |     | (Vaidya Agent)   |---->| hybrid_search()  |       
  +----------+     | - Gemini 2.5-fl  |     | - 3 prefetches   |       
                   | - Tools:         |     | - RRF fusion     |       
                   |   search_treatises|    | - rerank (BGE)   |       
                   |   get_verse_context|   +--------+---------+       
                   |   lookup_glossary |              |                
                   +---------+--------+               |                
                             |                         |                
                   +---------v--------+                |                
                   | AyurvedaContext  |<---------------+                
                   | Manager          |                                 
                   | - get_breadcrumb |                                 
                   | - get_contiguous |                                 
                   +------------------+                                 
                             |                                         
                   +---------v--------+                                 
                   | Gemini LLM       |                                 
                   | (gemini-2.5-flash|                                 
                   |  -lite)          |                                 
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
| Parser -> Database | Function call | `upload_to_qdrant(chunks, source, model)` |
| Python -> Qdrant | HTTP/gRPC SDK | `qdrant_client` Python SDK on localhost:6333 |
| Python -> GPU Sidecar | HTTP REST | `requests` POST to localhost:8080 |
| Agent -> LLM | SDK | `google.genai` SDK with function-calling tools |
| Agent -> Search Engine | Function call | `self.search_engine.search()` |

## Ingestion Pipeline (End-to-End)

1. Raw text loaded from `books/<treatise>/` (JSON or Markdown).
2. Samhita-specific parser (`CharakaParser`, `parse_shusrut_samhita`, `parse_astanga_hridaya`) traverses structure.
3. Parser outputs a list of chunk dicts with `id`, `level`, `parent_id`, `content`, `metadata`.
4. `unified_database.upload_to_qdrant()` or `AyurvedaDatabaseManager.upload_chunks()`:
   - Calls `RemoteEmbedder.encode()` for `dense_english` vector.
   - Calls `RemoteEmbedder.encode()` on normalized (Devanagari+IAST) text for `dense_sanskrit` vector.
   - Calls `RemoteEmbedder.encode_sparse()` for `sparse_splade` vector.
   - Builds `models.PointStruct` with named vectors and payload.
   - Upserts to Qdrant collection `ayurveda_rag` in batches of 50.

## Query Pipeline (End-to-End)

1. User enters natural-language query in CLI (`src/retriever/main.py`).
2. `AyurvedaRetriever.generate_answer()` creates a Gemini chat session with three tools.
3. Gemini agentic loop calls tools as needed.
4. `search_treatises` calls `AyurvedaSearchEngine.hybrid_search()`.
5. `hybrid_search` embeds query using E5 ("query: " prefix), normalizes for Sanskrit, gets SPLADE sparse vector, runs 3 parallel prefetches, fuses with RRF, reranks with BGE cross-encoder.
6. Results are filtered (score >= 0.15 threshold) and returned to agent.
7. Agent may call `get_verse_context` for contiguous verses or `lookup_glossary` for term resolution.
8. Agent synthesizes final answer in Siddhanta format.
