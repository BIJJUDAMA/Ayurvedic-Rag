# Retrieval and Ranking

## Full Retrieval Pipeline

```
                         USER QUERY
                             |
                             v
              +------------------------------+
              |       AyurvedaRouter         |
              | - Extracts LLM Intent        |
              | - Parses Direct Citations    |
              | - Extracts Technical Terms   |
              +------------------------------+
                             |
                             v
              +------------------------------+
              |     AyurvedaRetriever        |
              |  (LLM Agent w/ Routing Hint) |
              +------------------------------+
                             |
                             v
              +------------------------------+
              |  AyurvedaSearchEngine        |
              |  hybrid_search(text_query)   |
              +------------------------------+
                             |
              +--------------+---------------+
              |              |               |
              v              v               v
     +-----------+   +-----------+   +---------------+
     | E5 Encode  |   | Normalize  |   | E5 Encode     |
     | (English)  |   | (IAST/Deva)|   | (Sanskrit)    |
     | "query: "  |   +-----------+   | "query: "     |
     | + query    |        |          | + normalized  |
     +-----+-----+        |          +-------+-------+
           |              v                  |
           |     +---------------+           |
           |     | SPLADE Sparse |           |
           |     | encode_sparse |           |
           |     | (normalized)  |           |
           |     +-------+------+            |
           |             |                   |
           +------+------+------+-----------+
                  |         |         |
                  v         v         v
         +-----------+ +-----------+ +---------------+
         | PREFETCH  | | PREFETCH  | | PREFETCH      |
         | dense_eng | | dense_san | | sparse_splade |
         | limit=100 | | limit=100 | | limit=50      |
         +-----+-----+ +-----+-----+ +-------+-------+
               |             |               |
               +------+------+------+-------+
                      |         |
                      v         v
               +--------------------+
               | RRF FUSION         |
               | FusionQuery(RRF)   |
               | limit=400          |
               | w/ Metadata Filters|
               +---------+----------+
                         |
                         v
               +--------------------+
               | CROSS-ENCODER      |
               | RERANK (BGE)       |
               | RemoteEmbedder     |
               | .rerank()          |
               +---------+----------+
                         |
                         v
               +--------------------+
               | SCORE BOOST & MMR  |
               | exp(score * 3)     |
               | diversity filter   |
               +---------+----------+
                         |
                         v
               +--------------------+
               | TOP 5 RESULTS      |
               | context expanded   |
               +--------------------+
```

## Agentic Metadata Routing (Self-Querying)

Before hitting the vector database, the query is pre-processed by `AyurvedaRouter`:
1. **Direct Citation Parsing**: RegEx traps specific verse requests (e.g., `CS Su 1.1`).
2. **LLM Intent Classification**: Gemini Flash-Lite analyzes the query to output:
   - `intent`: (Chikitsa, Nidana, Sharira, Sutra, Sloka)
   - `technical_terms`: Core Sanskrit terms.
   - `treatise_preference`: Implied Samhita preference.

The Router generates "Routing Advice" which is injected into the Vaidya Agent's system prompt. The Agent then uses these parameters when calling the `search_treatises` tool to apply strict Qdrant `models.Filter` conditions (e.g., locking search to `source_treatise="shusrut_samhita"`).

## Hybrid Search Construction

### Query Embedding (3 vectors)

Performed in `AyurvedaSearchEngine.hybrid_search()`:

1. **English Dense Vector**:
   ```python
   semantic_query_vector = self.model.encode(f"query: {text_query}").tolist()
   ```

2. **Sanskrit Dense Vector** (transliteration bridge):
   ```python
   normalized_query = self._normalize_query(text_query)
   # Expands query with both Devanagari and IAST forms
   translit_query_vector = self.model.encode(f"query: {normalized_query}").tolist()
   ```

3. **SPLADE Sparse Vector**:
   ```python
   sparse_dict = self.model.encode_sparse(normalized_query)
   sparse_query_vector = SparseVector(indices=list(sparse_dict.keys()), values=list(sparse_dict.values()))
   ```

### Query Normalization

`_normalize_query()` in `search_engine.py`:
- If query contains Devanagari: transliterates to IAST and concatenates.
- If query is IAST/Latin: transliterates to Devanagari.

### Prefetch + RRF Fusion

Three parallel prefetches are sent to Qdrant via `client.query_points()`:

```python
prefetch = [
    models.Prefetch(query=semantic_vec, using="dense_english", limit=100),
    models.Prefetch(query=translit_vec, using="dense_sanskrit", limit=100),
    models.Prefetch(query=sparse_vec, using="sparse_splade", limit=50)
]
query = models.FusionQuery(fusion=models.Fusion.RRF)
limit = 400  # Broad candidate pool for reranker
```

RRF (Reciprocal Rank Fusion) merges the three ranked lists, applying `treatise_filter` and `intent_filter` to ensure precision.

### Reranking Step

After RRF fusion, the 400 candidates are reranked by a Cross-Encoder:

```python
candidate_texts = [f"[Source: {p.payload.get('source')}] Content: {p.payload.get('content')}" for p in candidates]
rerank_scores = self.model.rerank(text_query, candidate_texts)
```

The reranker is **BAAI/bge-reranker-base** running on the GPU sidecar. Cross-encoders process the query and chunk *together*, scoring their exact logical relationship, dramatically boosting Context Precision.

### Scoring and MMR

```python
boosted_score = np.exp(raw_score * 3.0)
```
The raw cross-encoder score is exponentially boosted to widen the margins for the LLM agent. 
An MMR (Maximal Marginal Relevance) diversity filter (`lambda=0.7`) is then applied to ensure the Top 5 results are not mathematically redundant (e.g., heavily penalizing chunks from the exact same chapter if they overlap too much).

## Agent's Use of Retrieval Results

In `AyurvedaRetriever.search_treatises()`:
1. Calls `self.search_engine.search()` which delegates to `hybrid_search()`.
2. Results are natively expanded with `context_manager.expand_context()` (fetching preceding/succeeding verses and hierarchical breadcrumb).
3. The LLM agent receives the formatted string and decides:
   - Whether results are sufficient.
   - Whether to call `get_verse_context` for deeper sequential logic.
   - Whether to call `lookup_glossary` to resolve terms.

## Query Expansion (Non-LLM)

Currently, query expansion occurs via:
1. The IAST/Devanagari transliteration bridge in `_normalize_query()`.
2. The LLM Router extracting `technical_terms` and feeding them to the search engine as supplementary context strings during RRF.
*(Future capability: Query Translation/HyDE via LLM - See Roadmap).*