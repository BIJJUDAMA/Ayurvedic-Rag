import os
import json
import networkx as nx
import argparse
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from src.retriever.search_engine import AyurvedaSearchEngine
from src.retriever.context_manager import AyurvedaContextManager

def generate_semantic_view(query: str, output_file: str = "visualize_semantic_result.html"):
    client = QdrantClient(host="localhost", port=6333)
    collection_name = "ayurveda_samhitas"
    
    # Load model
    model_path = os.path.join("models", "nomic-embed-text-v2-moe")
    actual_model = model_path if os.path.exists(model_path) else "nomic-ai/nomic-embed-text-v2-moe"
    print(f"Loading embedding model: {actual_model}...")
    model = SentenceTransformer(actual_model, trust_remote_code=True)
    
    print(f"Computing semantic similarity for query: '{query}'...")
    query_vector = model.encode(query).tolist()
    
    # Fetch TOP 300 matches
    semantic_hits = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=300,
        with_payload=True
    )
    
    # doc_id -> score
    scores = {str(hit.id): hit.score for hit in semantic_hits.points}
    print(f"Found {len(scores)} semantic matches.")

    # Fetch ALL points for the base graph (positions)
    print("Fetching full graph structure...")
    all_points = []
    next_offset = None
    while True:
        res, next_offset = client.scroll(
            collection_name=collection_name,
            limit=500,
            offset=next_offset,
            with_payload=True,
            with_vectors=False
        )
        all_points.extend(res)
        if not next_offset:
            break
            
    G = nx.Graph()
    
    # Mapping for different levels
    colors = {
        "book": "#a64dff",
        "sthana_index": "#a64dff",
        "chapter": "#ff4d4d",
        "section": "#4da6ff",
        "verse": "#4dff4d",
        "verse_block": "#4dff4d",
        "unknown": "#cccccc"
    }

    print(f"Building graph with {len(all_points)} nodes...")
    for point in all_points:
        payload = point.payload
        node_id = str(point.id)
        level = payload.get("level", "unknown")
        
        # Determine base attributes
        G.add_node(node_id, 
                   label=payload.get("title") or payload.get("section_title") or node_id[:8],
                   color=colors.get(level, colors["unknown"]),
                   size=15 if level in ["book", "sthana_index", "chapter"] else 5,
                   treatise=payload.get("source_treatise", "unknown"),
                   level=level,
                   semantic_score=scores.get(node_id, 0))

    # Add edges (Hierarchy + Sequence)
    for point in all_points:
        payload = point.payload
        node_id = str(point.id)
        parent_id = payload.get("parent_id")
        if parent_id and str(parent_id) in G:
            G.add_edge(str(parent_id), node_id, type="parent")
        next_id = payload.get("next_id")
        if next_id and str(next_id) in G:
            G.add_edge(node_id, str(next_id), type="next")

    print("Calculating layout positions...")
    pos = nx.spring_layout(G, k=0.15, iterations=50, seed=42)
    
    sigma_data = {"nodes": [], "edges": []}
    for node_id in G.nodes():
        node_data = G.nodes[node_id]
        x, y = pos[node_id]
        sigma_data["nodes"].append({
            "key": node_id,
            "attributes": {
                "x": float(x * 2000),
                "y": float(y * 2000),
                "label": node_data["label"],
                "color": node_data["color"],
                "size": node_data["size"],
                "treatise": node_data["treatise"],
                "level": node_data["level"],
                "score": node_data["semantic_score"]
            }
        })
        
    for i, (u, v) in enumerate(G.edges()):
        sigma_data["edges"].append({
            "key": f"e{i}",
            "source": u,
            "target": v,
            "attributes": {"color": "#333333", "size": 1}
        })

    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Ayurveda Semantic Galaxy: {query}</title>
    <style>
        body {{ margin: 0; padding: 0; background: #050505; color: white; font-family: sans-serif; overflow: hidden; }}
        #container {{ width: 100vw; height: 100vh; }}
        #overlay {{ position: absolute; top: 20px; left: 20px; background: rgba(0,0,0,0.8); padding: 20px; border-radius: 8px; border: 1px solid #444; z-index: 10; width: 300px; }}
        .score-bar {{ height: 5px; background: linear-gradient(to right, #111, #ffcc00); margin-top: 10px; }}
        h3 {{ color: #ffcc00; margin: 0 0 10px 0; }}
        p {{ font-size: 13px; color: #aaa; }}
        #tooltip {{ position: absolute; display: none; background: rgba(0,0,0,0.9); padding: 10px; border: 1px solid #ffcc00; border-radius: 4px; pointer-events: none; z-index: 20; max-width: 250px; }}
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="overlay">
        <h3>Semantic Search</h3>
        <p><b>Query:</b> "{query}"</p>
        <p>Nodes are highlighted based on their semantic similarity to the query using Nomic Embeddings.</p>
        <div class="score-bar"></div>
        <p><small>Intensity represents Similarity Score</small></p>
    </div>
    <div id="tooltip"></div>

    <script src="lib/sigma/graphology.min.js"></script>
    <script src="lib/sigma/sigma.min.js"></script>

    <script>
        const data = {json.dumps(sigma_data)};
        const container = document.getElementById("container");
        const graph = new (window.graphology || graphology)();

        data.nodes.forEach(n => graph.addNode(n.key, n.attributes));
        data.edges.forEach(e => graph.addEdge(e.source, e.target, e.attributes));

        const renderer = new Sigma(graph, container, {{
            renderEdgeLabels: false,
            labelColor: {{ color: "#666" }},
            defaultEdgeColor: "#222",
            minCameraZoom: 0.001
        }});

        renderer.setSetting("nodeReducer", (node, data) => {{
            const res = {{ ...data }};
            const score = data.score || 0;
            
            if (score > 0) {{
                // Highlighted Semantic Node
                res.size = res.size * (1 + score * 1.5);
                // Gradient from Red (low similarity) to Yellow (high similarity)
                const intensity = Math.floor(score * 255);
                res.color = `rgb(255, ${{intensity}}, 0)`;
                res.zIndex = 1;
            }} else {{
                // Background Node
                res.color = "#111";
                res.label = "";
                res.zIndex = -1;
            }}
            return res;
        }});

        renderer.setSetting("edgeReducer", (edge, data) => {{
            const res = {{ ...data }};
            const source = graph.source(edge);
            const target = graph.target(edge);
            const sScore = graph.getNodeAttribute(source, "score") || 0;
            const tScore = graph.getNodeAttribute(target, "score") || 0;
            
            if (sScore > 0.5 && tScore > 0.5) {{
                res.color = "#ffcc00";
                res.size = 2;
            }} else {{
                res.hidden = true;
            }}
            return res;
        }});

        // Tooltip
        const tooltip = document.getElementById("tooltip");
        renderer.on("enterNode", ({{ node }}) => {{
            const attr = graph.getNodeAttributes(node);
            if (attr.score > 0) {{
                tooltip.style.display = "block";
                tooltip.innerHTML = `<strong>${{attr.label}}</strong><br>Similarity: ${{attr.score.toFixed(4)}}<br><small>${{attr.level}}</small>`;
            }}
        }});
        renderer.on("leaveNode", () => tooltip.style.display = "none");
        window.addEventListener("mousemove", (e) => {{
            tooltip.style.left = (e.clientX + 20) + "px";
            tooltip.style.top = (e.clientY + 20) + "px";
        }});

    </script>
</body>
</html>
"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Semantic view generated: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--q", type=str, required=True, help="Query to visualize semantically")
    args = parser.parse_args()
    
    safe_name = "".join([c if c.isalnum() else "_" for c in args.q])[:30]
    output = f"visualize_semantic_{safe_name}.html"
    generate_semantic_view(args.q, output)
