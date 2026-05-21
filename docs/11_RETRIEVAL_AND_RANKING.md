# Retrieval and Ranking

## Full Retrieval Pipeline

```
                         USER QUERY
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
         | limit=60  | | limit=60  | | limit=60      |
         +-----+-----+ +-----+-----+ +-------+-------+
               |             |               |
               +------+------+------+-------+
                      |         |
                      v         v
               +--------------------+
               | RRF FUSION         |
               | FusionQuery(RRF)   |
               | limit=60           |
               +---------+----------+
                         |
                         v
               +--------------------+
               | 60 CANDIDATES     |
               +---------+----------+
                         |
                         v
               +--------------------+
               | CROSS-ENCODER     |
               | RERANK (BGE)      |
               | RemoteEmbedder    |
               | .rerank()         |
               +---------+----------+
                         |
                         v
               +--------------------+
               | SCORE FILTER      |
               | threshold >= 0.15 |
               | boost: (s+1)^2   |
               +---------+----------+
                         |
                         v
               +--------------------+
               | TOP 5 RESULTS     |
               | sorted descending |
               +--------------------+
```

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
   # e.g., "agni" -> "agni अग्नि"
   translit_query_vector = self.model.encode(f"query: {normalized_query}").tolist()
   ```

3. **SPLADE Sparse Vector**:
   ```python
   sparse_dict = self.model.encode_sparse(normalized_query)
   sparse_query_vector = SparseVector(indices=list(sparse_dict.keys()), values=list(sparse_dict.values()))
   ```

### Query Normalization

`_normalize_query()` in `search_engine.py`:
- If query contains Devanagari (`\u0900-\u097F`): transliterates to IAST and concatenates: `f"{query} {iast}"`
- If query is IAST/Latin: transliterates to Devanagari: `f"{query} {dev}"`
- Falls back to original query on error.

### Prefetch + RRF Fusion

Three parallel prefetches are sent to Qdrant via `client.query_points()`:

```python
prefetch = [
    models.Prefetch(query=semantic_vec, using="dense_english", limit=60),
    models.Prefetch(query=translit_vec, using="dense_sanskrit", limit=60),
    models.Prefetch(query=sparse_vec, using="sparse_splade", limit=60)
]
query = models.FusionQuery(fusion=models.Fusion.RRF)
limit = 60  # fused candidate pool
```

Optional `treatise_filter` adds a `Filter(must=[FieldCondition(key="source_treatise", match=MatchValue(value=treatise))])` to all prefetches.

RRF (Reciprocal Rank Fusion) merges the three ranked lists. A chunk appearing at rank 1 in all three lists gets the highest fused score.

### Reranking Step

After RRF fusion, the 60 candidates are reranked by a Cross-Encoder:

```python
candidate_texts = [f"[Source: {p.payload.get('source_treatise')}] Content: {p.payload.get('content')}" for p in candidates]
rerank_scores = self.model.rerank(text_query, candidate_texts)
```

The reranker is **BAAI/bge-reranker-base** running on the GPU sidecar.

### Scoring and Filtering

```python
SCORE_THRESHOLD = 0.15
boosted_score = np.power(raw_score + 1.0, 2)

# Filter: raw_score >= 0.15
# Then sort by boosted_score descending
# Return top_k = 5
```

The threshold of 0.15 filters out low-relevance results. The boost `(score + 1)^2` amplifies differences for the agent's ranking view.

## Agent's Use of Retrieval Results

In `AyurvedaRetriever.search_treatises()`:
1. Calls `self.search_engine.search()` which delegates to `hybrid_search()`.
2. Results are formatted with SOURCE_ID, RELEVANCE_SCORE, HIERARCHICAL_PATH (breadcrumb), VERSE_CONTENT.
3. Results are printed in a Rich Panel for the human operator.
4. The LLM agent receives the formatted string and decides:
   - Whether results are sufficient (rules in tool docstring).
   - Whether to call `get_verse_context` for anaphoric verses.
   - Whether to call `lookup_glossary` to resolve terms.
   - Whether to discard contextually irrelevant results (e.g., "stiff eyes" vs "stiff body").

### Tool-Specific Retrieval: `lookup_glossary`

The `lookup_glossary` tool uses a different query pattern:
- Same 3-vector prefetch + RRF.
- Filter restricts to `level = "stub_glossary"` OR `level = "stub_botanical"`.
- Lower prefetch limits (10 per vector).
- Returns TERM_ENTRY and DEFINITION.

### Tool-Specific Retrieval: `get_verse_context`

Not a search — uses `client.retrieve()` by ID:
- Fetches the target point's payload.
- Calls `AyurvedaContextManager.expand_context()` which:
  - Walks `parent_id` chain recursively for breadcrumb.
  - Walks `prev_id` chain (window=1) for preceding verse.
  - Walks `next_id` chain (window=1) for succeeding verse.

## Context Manager

`AyurvedaContextManager` in `context_manager.py`:
- `get_breadcrumb(payload)`: Recursively follows `parent_id` from child to root, returns reversed list (root → child).
- `get_contiguous_block(payload, window=1)`: Follows `prev_id` and `next_id` chains with configurable window size.
- `expand_context(doc_id, payload)`: Combines both into a single dict.

## Query Expansion (Non-LLM)

Before retrieval, the only query expansion is the IAST/Devanagari transliteration bridge in `_normalize_query()`. There is NO:
- Query rewriting using LLM.
- Query decomposition.
- Synonym expansion beyond transliteration.
- Back-translation.

## E5 Prefix Convention

Following the `intfloat/multilingual-e5-large` convention:
- **Indexing**: `"passage: "` prefix added to chunk text before embedding (in `unified_database.py`).
- **Retrieval**: `"query: "` prefix added to user query before embedding (in `search_engine.py`).
