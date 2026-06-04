// 1. Establish Unique Constraints
CREATE CONSTRAINT IF NOT EXISTS FOR (f:Formulation) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:Plant) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Disease) REQUIRE d.id IS UNIQUE;

// 2. Ingest Nodes
LOAD CSV WITH HEADERS FROM 'file:///graph_nodes.csv' AS row
WITH row WHERE row.label = 'Formulation'
MERGE (f:Formulation {id: row.id})
ON CREATE SET f.name = row.name
SET f += apoc.convert.fromJsonMap(row.attributes);

LOAD CSV WITH HEADERS FROM 'file:///graph_nodes.csv' AS row
WITH row WHERE row.label = 'Plant'
MERGE (p:Plant {id: row.id})
ON CREATE SET p.name = row.name
SET p += apoc.convert.fromJsonMap(row.attributes);

LOAD CSV WITH HEADERS FROM 'file:///graph_nodes.csv' AS row
WITH row WHERE row.label = 'Disease'
MERGE (d:Disease {id: row.id})
ON CREATE SET d.name = row.name
SET d += apoc.convert.fromJsonMap(row.attributes);

// 3. Ingest Directed Relationships (Edges)
LOAD CSV WITH HEADERS FROM 'file:///graph_edges.csv' AS row
WITH row WHERE row.relationship = 'INGREDIENT_OF'
WITH row, apoc.convert.fromJsonMap(row.properties) AS props
MATCH (f:Formulation {id: row.source})
MATCH (p:Plant {id: props.pharmacopoeia_ref})
MERGE (f)-[r:INGREDIENT_OF]->(p)
SET r += props;

LOAD CSV WITH HEADERS FROM 'file:///graph_edges.csv' AS row
WITH row WHERE row.relationship = 'ASSOCIATED_WITH'
MATCH (f:Formulation {id: row.source})
MATCH (d:Disease {id: row.target})
MERGE (f)-[r:ASSOCIATED_WITH]->(d)
SET r += apoc.convert.fromJsonMap(row.properties);

// Note: For TREATMENT_FOR edges, let's verify if row.target might contain multiple values (e.g., separated by semicolon)
LOAD CSV WITH HEADERS FROM 'file:///graph_edges.csv' AS row
WITH row WHERE row.relationship = 'TREATMENT_FOR'
MATCH (p:Plant {id: row.source})
MATCH (d:Disease {id: row.target})
MERGE (p)-[r:TREATMENT_FOR]->(d)
SET r += apoc.convert.fromJsonMap(row.properties);
