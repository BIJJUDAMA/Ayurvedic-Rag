# Data Flow

## 1. Document Ingestion Flow (Raw Text to Stored Vector Point)

```
Step 1  src/chunking/<samhita>/main.py::main()
          Opens raw source file from books/<treatise>/ directory.
          For Charaka: iterates over *.json files, loads each.
          For Susruta/Astanga: opens .md file, reads lines.

Step 2  Parser class/function
          Charaka:  CharakaParser.parse(data)
          Susruta:  parse_shusrut_samhita(file_path)
          Astanga:  parse_astanga_hridaya(file_path)
          Returns List[Dict] with keys: id, level, parent_id, content, 
          metadata, prev_id, next_id.

Step 3  main.py calls book workers (Phase 1-3)
          Generates artifacts in processed-books/<treatise>/
          - canonical.md (sequential text)
          - vectors.jsonl (raw chunks)

Step 4  Phase 4: Semantic Cross-Linking (src/chunking/cross_linker.py)
          a) Loads all vectors.jsonl files.
          b) Extracts technical terms from glossary stubs and metadata.
          c) Builds inverted index: term -> [node_ids].
          d) Injects 'related_nodes' into chunk metadata sharing the same terms.
          e) Overwrites vectors.jsonl with enriched metadata.

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
          a) Extracts direct citations (e.g. CS Su 1.1)
          b) Uses LLM (gemini-2.5-flash-lite) to extract intent (Chikitsa, Nidana, etc.)
          c) Extracts technical_terms (Sanskrit core concepts)
          d) Determines treatise_preference
          e) Returns structured routing advice.

Step 3  Agent receives routing advice, calls search_treatises(query, intent, treatise)
          Inside AyurvedaRetriever.search_treatises():
            Calls AyurvedaSearchEngine.hybrid_search(original_query, ...)

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
          limit = 400 (broad candidate pool for reranker)
          (treatise_filter and intent filters applied to all prefetches if provided)

Step 6  Reranking via RemoteEmbedder.rerank(text_query, candidate_texts):
          candidate_texts = ["[Source: X] Content: Y" for each candidate]
          scores = BGE CrossEncoder predict

Step 7  Score Boosting & Filtering
          boosted_score = np.exp(raw_score * 3.0)
          Sort descending, take top_k * 2
          Apply MMR (Maximal Marginal Relevance) diversity filter -> Top 5
```

## 3. Agent Reasoning Flow (Retrieved Chunks to Final Answer)

```
Step 1  AyurvedaRetriever.generate_answer(query):
          Creates chat with Gemini, exposes tools
          system_instruction = "Vaidya - senior Ayurvedic scholar, Tikakara..." + routing_advice

Step 2  Gemini 2.5-flash-lite agentic loop:
          a) Reads routing advice (e.g. "Focus on Chikitsa contexts", "DIRECT CITATION DETECTED")
          b) If query is descriptive English -> MUST call lookup_glossary first
          c) Once Sanskrit term resolved -> call search_treatises with intent/treatise filters
          d) Check HIERARCHICAL_PATH and VERSE_CONTENT of results
          e) If anaphoric verses -> call get_verse_context
          f) After tool returns, agent decides if sufficient or needs more search

Step 3  Synthesis into Siddhanta format:
          - PRIMARY VERSE: Sanskrit + English
          - CORE PRINCIPLE: Grounded answer
          - CITATION: Treatise.Sthana.Chapter/Verse
          - CLASSICAL CONTEXT: Adhikarana explanation
          - CROSS-SAMHITA VIEW: Contrast if multiple treatises
          - LIMITATIONS: Parts not found in texts

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