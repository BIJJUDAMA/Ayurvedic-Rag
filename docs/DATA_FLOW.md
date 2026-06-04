# Data Flow

## 1. Document Ingestion Flow (Raw Text to Stored Vector Point)

```
Step 0  Phase 0: Knowledge Graph Ingestion (src/pre_processing/graph_ingest.py)
          - Executes cypher-shell inside Neo4j container.
          - Ingests graph_nodes.csv and graph_edges.csv into Neo4j.
          - Establishes clinical relationships (INGREDIENT_OF, TREATMENT_FOR).

Step 1  src/chunking/<samhita>/main.py::main()
          Opens raw source file from books/<treatise>/ directory.
          For Charaka: iterates over *.json files, loads each.
          For Susruta/Astanga: opens .md file, reads lines.

Step 2  Parser class/function
          Charaka:  CharakaParser.parse(data) [Bilingual Pairing]
          Susruta:  parse_shusrut_samhita(file_path)
          Astanga:  parse_astanga_hridaya(file_path) [Bilingual Pairing]
          Returns List[Dict] with keys: id, level, parent_id, content, 
          metadata (linguistic_type, adhikarana), prev_id, next_id.

Step 3  main.py calls book workers (Phase 1-3)
          Generates artifacts in processed-books/<treatise>/
          - canonical.md (sequential text)
          - vectors.jsonl (raw chunks)

Step 4  Phase 4: Semantic Cross-Linking (src/chunking/cross_linker.py)
          a) Loads all vectors.jsonl files.
          b) Loads graph entities from graph/data/graph_nodes.csv.
          c) Internal Linking: term-to-id inverted index.
          d) Neo4j Linking: Scans content/titles for clinical entity names.
          e) Injects 'related_nodes' AND 'neo4j_entities' (IDs) into metadata.
          f) Overwrites vectors.jsonl with enriched metadata.

Step 5  Phase 5: Unified Upload (src/chunking/uploader.py)
          AyurvedaUploader.upload_book(book_dir):
          For each chunk in enriched vectors.jsonl:
            a) content = chunk["content"]
            b) title = chunk.get("title") or ""
            c) indexing_prefix = "passage: "

Step 6  Vector generation via RemoteEmbedder (GPU Sidecar HTTP POST):
          a) dense_english = RemoteEmbedder.encode("passage: " + title + content)
          b) sanskrit_context = _normalize_sanskrit(title + content)
          c) dense_sanskrit = RemoteEmbedder.encode("passage: " + sanskrit_context)
          d) sparse_dict = RemoteEmbedder.encode_sparse(title + content)

Step 7  Build PointStruct:
          id = chunk["id"]
          vector = { dense_english, dense_sanskrit, sparse_splade }
          payload = { source, level, content, parent_id, prev_id, next_id, metadata }

Step 8  Client.upsert() in batches of 32
          collection_name = "ayurveda_rag"
```

## 2. Query Resolution Flow (User Query to Retrieved Chunks)

```
Step 1  src/retriever/vaidya_engine.py::AyurvedaRetriever.generate_answer(query)
          Resets session_hits = {}
          Calls AyurvedaRouter.route(query) to analyze query intent.

Step 2  AyurvedaRouter Analysis
          a) Extracts direct citations.
          b) Uses LLM (gemini-2.5-flash-lite) to extract intent (Chikitsa, Nidana, etc.)
          c) Extracts technical_terms (Sanskrit core concepts)
          d) Detects clinical_entities (MANDATORY_GRAPH_LOOKUP trigger).

Step 3  Agentic Execution (Siddhanta-Pramana Handshake)
          a) MANDATORY: Call query_knowledge_graph(entity_name) to get Canonical ID.
          b) SEARCH: Call search_treatises(query) using canonical terms.
          c) PIVOT: Cross-reference 'metadata.neo4j_entities' with Graph ID.
             - Match = Signal; No-Match = Linguistic Noise.

Step 4  AyurvedaSearchEngine.hybrid_search(text_query):
          a) query_prefix = "query: "
          b) semantic_query_vector = RemoteEmbedder.encode("query: " + text_query)
          c) normalized_query = _normalize_query(text_query)  [IAST<->Devanagari]
          d) translit_query_vector = RemoteEmbedder.encode("query: " + normalized_query)
          e) sparse_dict = RemoteEmbedder.encode_sparse(normalized_query)
          f) sparse_query_vector = SparseVector(indices, values)

Step 5  Qdrant client.query_points():
          prefetch = [
            (query=semantic_vec, using="dense_english", limit=100),
            (query=translit_vec, using="dense_sanskrit", limit=100),
            (query=sparse_vec, using="sparse_splade", limit=50)
          ]
          query = FusionQuery(fusion=RRF)
          limit = 400 (Full candidate pool for expert reranking)

Step 6  Reranking via RemoteEmbedder.rerank(text_query, candidate_texts):
          candidate_texts = ["[Source: X] Content: Y" for each candidate]
          scores = BGE CrossEncoder (reranks all 400 candidates)

Step 7  Score Boosting & Filtering
          boosted_score = np.exp(raw_score * 3.0)
          Sort descending, take top_k * 4
          Apply MMR (Maximal Marginal Relevance) lambda=0.8 (Precision-biased) -> Top 5
```

## 3. Agent Reasoning Flow (Retrieved Chunks to Final Answer)

```
Step 1  AyurvedaRetriever.generate_answer(query):
          Creates chat with Gemini, exposes tools
          system_instruction = "Vaidya - Siddhanta-Pramana Workflow..."

Step 2  Gemini 2.5-flash-lite agentic loop:
          a) Establish Siddhanta: call query_knowledge_graph.
          b) Find Pramana: call search_treatises using Graph facts.
          c) Use 'stub_glossary' as Definition Anchors (Final Heading).
          d) Graph-Verse Validation: Flag "Textual Gaps" if Graph fact isn't in Verse.
          e) Relational Hopping: Traverses INGREDIENT_OF links to find related verses.

Step 3  Synthesis into Scholarly Siddhanta format:
          - HEADING: Canonical Definition from stub_glossary
          - SIDDHANTA: Validated facts from Neo4j (Dosage, Ingredients)
          - PRAMANA: Sanskrit Shloka + English Translation (Matching IDs)
          - VALIDATION: Explicit "Siddhanta-Pramana Samyoga" statement.

Step 4  Return (sorted_hits, answer_text)

Step 5  src/retriever/main.py renders:
          - Panel with Markdown answer
          - Source evidence trail (score, path, content)
```

## 4. Evaluation Flow

```
Step 1  src/evaluation/run_eval.py::main()
          Initializes AyurvedaRetriever
          Creates ProductionAgentWrapper (calls generate_answer internally)

Step 2  run_evaluation(wrapper, dataset.json, retriever)
          For each item in dataset.json:
            a) query = item["query"], expected_id = item["expected_id"]
            b) search_results = wrapper.search(query, top_k=20)
            c) Extract titles from results
            d) calculate_recall_at_k(result_ids, expected_id, k) 
               uses is_match() cascade:
                 - normalize_id string match
                 - semantic_similarity_match (cosine > 0.85 via E5)
                 - cross_encoder_match (rerank score > 0.7)
                 - llm_judge_match (Gemini-as-judge)
            e) calculate_mrr(result_ids, expected_id)
          Aggregate: recall@5, recall@10, MRR

Step 3  run_ragas_evaluation(wrapper, dataset.json)
          For each item:
            a) contexts = wrapper.search(query, top_k=5) -> extract text
            b) Append to Dataset dictionary
          Run Ragas evaluate() with:
            - context_precision
            - context_recall (if ground_truth available)
            - faithfulness
            - answer_relevancy
          Uses LangchainLLMWrapper(ChatGoogleGenerativeAI("gemini-2.5-flash-lite"))
          Uses robust retry logic for API congestion (503s).

Step 4  print_final_health_report():
          Status: EXCELLENT (MRR>0.4 and precision>0.6)
                  STABLE (MRR>0.2)
                  CRITICAL (MRR<=0.2)
```