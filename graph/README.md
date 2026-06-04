# GRAYU Neo4j Containerized Knowledge Graph Import

## Contents

* **`docker-compose.yml`**: Docker service definition running Neo4j with the APOC plugin enabled and secure procedure privileges pre-configured.
* **`data/`**: Subfolder containing the CSV datasets and the automation import script:
  * `graph_nodes.csv` (Node data)
  * `graph_edges.csv` (Edge and relationship property data)
  * `import.cypher` (Automated ingestion script that establishes constraints, imports nodes, and connects all relationships)

---

## Spin Up the Neo4j Container

```bash
docker compose up -d
```

Database Credentials are pre-configured in `docker-compose.yml`:

* **Username**: `neo4j`
* **Password**: `1234`

---

## Access the Neo4j Browser

Open your web browser and navigate to:

* **URL**: [http://localhost:7474](http://localhost:7474)
* Log in using the credentials listed in Step 1.

---

## Run the Import Cypher Queries

### Option A: One-Command Automated Ingest (Recommended)

You can run the entire import process (unique constraints, nodes, and relationships) automatically with a single command. Open your terminal and run:

```bash
docker exec grayu-neo4j cypher-shell -u neo4j -p 1234 -f /var/lib/neo4j/import/import.cypher
```

### Option B: Manual Ingest (Browser Copy-Paste)

Alternatively, you can copy-paste and execute the following Cypher blocks one by one in the Neo4j Browser query editor:

### 1. Establish Unique Constraints

Optimizes lookup indexing for fast node-to-node mapping.

```cypher
CREATE CONSTRAINT IF NOT EXISTS FOR (f:Formulation) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:Plant) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Disease) REQUIRE d.id IS UNIQUE;
```

### 2. Ingest Nodes

Loads formulations, plants, and diseases, automatically converting inner JSON strings back into rich native attributes.

#### A. Formulation Nodes

```cypher
LOAD CSV WITH HEADERS FROM 'file:///graph_nodes.csv' AS row
WITH row WHERE row.label = 'Formulation'
CREATE (f:Formulation {id: row.id, name: row.name})
SET f += apoc.convert.fromJsonMap(row.attributes);
```

#### B. Plant Nodes

```cypher
LOAD CSV WITH HEADERS FROM 'file:///graph_nodes.csv' AS row
WITH row WHERE row.label = 'Plant'
CREATE (p:Plant {id: row.id, name: row.name})
SET p += apoc.convert.fromJsonMap(row.attributes);
```

#### C. Disease Nodes

```cypher
LOAD CSV WITH HEADERS FROM 'file:///graph_nodes.csv' AS row
WITH row WHERE row.label = 'Disease'
CREATE (d:Disease {id: row.id, name: row.name})
SET d += apoc.convert.fromJsonMap(row.attributes);
```

### 3. Ingest Directed Relationships (Edges)

Unpacks quantities, parts used, references, and attributes onto the directed connections.

#### A. Formulation -> Plant (`INGREDIENT_OF`)

Matches on the botanical scientific name located inside the properties column (`pharmacopoeia_ref`).

```cypher
LOAD CSV WITH HEADERS FROM 'file:///graph_edges.csv' AS row
WITH row WHERE row.relationship = 'INGREDIENT_OF'
WITH row, apoc.convert.fromJsonMap(row.properties) AS props
MATCH (f:Formulation {id: row.source})
MATCH (p:Plant {id: props.pharmacopoeia_ref})
MERGE (f)-[r:INGREDIENT_OF]->(p)
SET r += props;
```

#### B. Formulation -> Disease (`ASSOCIATED_WITH`)

```cypher
LOAD CSV WITH HEADERS FROM 'file:///graph_edges.csv' AS row
WITH row WHERE row.relationship = 'ASSOCIATED_WITH'
MATCH (f:Formulation {id: row.source})
MATCH (d:Disease {id: row.target})
MERGE (f)-[r:ASSOCIATED_WITH]->(d)
SET r += apoc.convert.fromJsonMap(row.properties);
```

#### C. Plant -> Disease (`TREATMENT_FOR`)

```cypher
LOAD CSV WITH HEADERS FROM 'file:///graph_edges.csv' AS row
WITH row WHERE row.relationship = 'TREATMENT_FOR'
MATCH (p:Plant {id: row.source})
MATCH (d:Disease {id: row.target})
MERGE (p)-[r:TREATMENT_FOR]->(d)
SET r += apoc.convert.fromJsonMap(row.properties);
```

---

## Verify Database Ingestion

Ensure the graph has been constructed correctly by executing these verification checks:

### Count Nodes by Type

```cypher
MATCH (n)
RETURN labels(n) AS Label, count(n) AS NodeCount
ORDER BY NodeCount DESC;
```

### Count Edges by Type

```cypher
MATCH ()-[r]->()
RETURN type(r) AS RelationshipType, count(r) AS EdgeCount
ORDER BY EdgeCount DESC;
```

---

## Visualize the Data

Run these queries in the Neo4j Browser to explore and visualize the ingested graphs interactive:

### 1. View general overview of the graph

```cypher
MATCH (n) RETURN n LIMIT 100;
```

### 2. View Formulations and their Plant ingredients

```cypher
MATCH (f:Formulation)-[r:INGREDIENT_OF]->(p:Plant)
RETURN f, r, p LIMIT 50;
```

### 3. View Plants and the Diseases they treat

```cypher
MATCH (p:Plant)-[r:TREATMENT_FOR]->(d:Disease)
RETURN p, r, d LIMIT 50;
```

### 4. View end-to-end connections (Formulation -> Plant -> Disease)

```cypher
MATCH (f:Formulation)-[r1:INGREDIENT_OF]->(p:Plant)-[r2:TREATMENT_FOR]->(d:Disease)
RETURN f, r1, p, r2, d LIMIT 30;
```
