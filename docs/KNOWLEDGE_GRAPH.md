# Knowledge Graph (Neo4j)

The Knowledge Graph (KG) serves as the "Siddhanta" (Canonical Truth) layer of the Ayurveda RAG system. While Qdrant provides semantic context and original verses, Neo4j stores validated clinical relationships between Diseases, Plants, and Formulations.

## 1. Schema Definition

The graph uses three primary node labels and three relationship types:

### Nodes
- **Formulation**: Compound medicines (e.g., Abhayarista).
- **Plant**: Botanical entities (e.g., Haritaki).
- **Disease**: Clinical conditions (e.g., Arsha).

### Relationships
- `INGREDIENT_OF`: Links a **Plant** to a **Formulation**.
- `TREATMENT_FOR`: Links a **Plant** or **Formulation** to a **Disease**.
- `ASSOCIATED_WITH`: General clinical association between entities.

## 2. Data Ingestion

The ingestion process is containerized and automated via `src/pre_processing/graph_ingest.py`.

### Ingestion Flow:
1.  **CSV Source**: Data is maintained in `graph/data/graph_nodes.csv` and `graph/data/graph_edges.csv`.
2.  **Cypher Execution**: The `ingest_graph()` function executes `import.cypher` inside the `grayu-neo4j` container.
3.  **Unique Constraints**: Establishing constraints on `id` and `name` properties.
4.  **APOC Integration**: Uses the APOC plugin to parse JSON-formatted properties within the CSVs.

## 3. Agentic Tooling: `Neo4jGraphTool`

Located in `src/retriever/graph_tool.py`, this tool allows the Vaidya agent to perform structured lookups.

### Key Query: `query_knowledge_graph(entity_name)`
- **Action**: Performs a case-insensitive fuzzy match on node names.
- **Siddhanta Mandate**: This is the mandatory first step for any clinical query involving a specific Disease, Plant, or Formulation.
- **Output**: Returns node attributes (dosage, preparation) and a list of all validated relationships (incoming and outgoing).
- **Directionality**: 
  - `OUT`: Entity $\rightarrow$ Target (e.g., Formulation $\rightarrow$ Ingredient).
  - `IN`: Source $\rightarrow$ Entity (e.g., Ingredient $\leftarrow$ Formulation).

## 4. Metadata Bridging (The Handshake)

The bridge allows the retriever to move from a "fuzzy" semantic search result to a "precise" graph lookup. The Agent compares the ID returned by `Neo4jGraphTool` with the `metadata.neo4j_entities` field in Qdrant results. 

**This Handshake enables:**
1. **Noise Filtering**: Excluding verses that mention a term linguistically but not clinically.
2. **Relational Hopping**: Discovering ingredients via Neo4j and immediately searching Qdrant for their specific verses.
3. **Anchor Utilization**: Using `stub_glossary` chunks as semantic definitions grounded in the Graph's canonical IDs.

## 5. Visualizer (Graph Galaxy)

The `graph/visualizer.html` provides a WebGL-powered interactive view of the knowledge graph. 
- **Core (Red)**: Formulations.
- **Middle (Green)**: Plants.
- **Outer (Blue)**: Diseases.

This tool is used for auditing the integrity of clinical relationships across the three Samhitas.
