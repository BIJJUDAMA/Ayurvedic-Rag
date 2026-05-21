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

Step 3  main.py calls upload_to_qdrant(chunks, source_treatise, model)
          from src.chunking.unified_database

Step 4  AyurvedaDatabaseManager.upload_chunks(chunks, source_treatise)
          For each chunk:
            a) content = chunk["content"]
            b) title = chunk.get("section_title") or chapter_title or ""
            c) indexing_prefix = "passage: "

Step 5  Vector generation via RemoteEmbedder (GPU Sidecar HTTP POST):
          a) dense_english = RemoteEmbedder.encode("passage: " + title + content)
          b) sanskrit_context = _normalize_sanskrit(title + content)
                        [Devanagari+IAST combined]
          c) dense_sanskrit = RemoteEmbedder.encode("passage: " + sanskrit_context)
          d) sparse_dict = RemoteEmbedder.encode_sparse(title + content)
          e) sparse_vec = SparseVector(indices=sparse_dict.keys(), values=sparse_dict.values())

Step 6  Build PointStruct:
          id = chunk["id"] (UUID v5 string)
          vector = { dense_english, dense_sanskrit, sparse_splade }
          payload = { source_treatise, level, content, parent_id, prev_id, 
                     next_id, **metadata }

Step 7  Client.upsert() in batches of 50
          collection_name = "ayurveda_rag"
```

## 2. Query Resolution Flow (User Query to Retrieved Chunks)

```
Step 1  src/retriever/vaidya_engine.py::AyurvedaRetriever.generate_answer(query)
          Resets session_hits = {}
          Creates chat with Gemini, exposes tools

Step 2  LLM calls search_treatises(query, intent, treatise)
          Inside AyurvedaRetriever.search_treatises():
            Calls AyurvedaSearchEngine.search(original_query, ...)

Step 3  AyurvedaSearchEngine.search() calls hybrid_search(text_query, top_k=5)

Step 4  AyurvedaSearchEngine.hybrid_search(text_query):
          a) query_prefix = "query: "
          b) semantic_query_vector = RemoteEmbedder.encode("query: " + text_query)
          c) normalized_query = _normalize_query(text_query)  [IAST<->Devanagari]
          d) translit_query_vector = RemoteEmbedder.encode("query: " + normalized_query)
          e) sparse_dict = RemoteEmbedder.encode_sparse(normalized_query)
          f) sparse_query_vector = SparseVector(indices, values)

Step 5  Qdrant client.query_points():
          prefetch = [
            (query=semantic_vec, using="dense_english", limit=60),
            (query=translit_vec, using="dense_sanskrit", limit=60),
            (query=sparse_vec, using="sparse_splade", limit=60)
          ]
          query = FusionQuery(fusion=RRF)
          limit = 60
          (treatise_filter applied if provided)

Step 6  Reranking via RemoteEmbedder.rerank(text_query, candidate_texts):
          candidate_texts = ["[Source: X] Content: Y" for each candidate]
          scores = BGE CrossEncoder predict

Step 7  Filter: score >= 0.15 (SCORE_THRESHOLD)
          Boost: boosted_score = np.power(raw_score + 1.0, 2)
          Sort descending, return top_k=5
```

## 3. Agent Reasoning Flow (Retrieved Chunks to Final Answer)

```
Step 1  AyurvedaRetriever.generate_answer(query):
          session_hits = {}
          tools = [search_treatises, get_verse_context, lookup_glossary]
          system_instruction = "Vaidya - senior Ayurvedic scholar, Tikakara..."

Step 2  Gemini 2.5-flash-lite agentic loop:
          a) If query is descriptive English -> MUST call lookup_glossary first
          b) Once Sanskrit term resolved -> call search_treatises
          c) Check HIERARCHICAL_PATH and VERSE_CONTENT of results
          d) If anaphoric verses -> call get_verse_context
          e) After tool returns, agent decides if sufficient or needs more search
          f) Max ~3 search queries, ~2 context retrievals

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
          Uses LangchainLLMWrapper(ChatGoogleGenerativeAI("gemini-2.5-flash-lite"))

Step 4  print_final_health_report():
          Status: EXCELLENT (MRR>0.4 and precision>0.6)
                  STABLE (MRR>0.2)
                  CRITICAL (MRR<=0.2)
```
