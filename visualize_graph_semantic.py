import sys
import os
import re
import json
import networkx as nx
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from qdrant_client import QdrantClient
from qdrant_client.http import models
from indic_transliteration import sanscript
from indic_transliteration.sanscript import SCHEMES, transliterate

# Import local RemoteEmbedder
from src.chunking.remote_embedder import RemoteEmbedder

# 1. Add project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# --- Configuration ---
COLLECTION_NAME = "ayurveda_rag"

# --- Initialization ---
app = Flask(__name__)
client = QdrantClient(host="localhost", port=6333)

print("Connecting to GPU Embedding Sidecar...")
dense_model = RemoteEmbedder()
if not dense_model.is_available():
    print("Warning: GPU Sidecar not reachable at http://localhost:8080. Start it with docker-compose up -d")

cached_graph_data = None

def _normalize_query(query: str) -> str:
    """Expand query with Devanagari/IAST to catch all linguistic variants."""
    try:
        has_dev = bool(re.search(r'[\u0900-\u097F]', query))
        if has_dev:
            iast = transliterate(query, sanscript.DEVANAGARI, SCHEMES[sanscript.IAST])
            return f"{query} {iast}"
        else:
            dev = transliterate(query, sanscript.IAST, SCHEMES[sanscript.DEVANAGARI])
            return f"{query} {dev}"
    except:
        return query

def get_graph_structure():
    global cached_graph_data
    if cached_graph_data:
        return cached_graph_data

    print(f"Fetching full graph structure from Qdrant ('{COLLECTION_NAME}')...")
    if not client.collection_exists(COLLECTION_NAME):
        return {"nodes": [], "edges": []}

    all_points = []
    next_offset = None
    while True:
        res, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=500,
            offset=next_offset,
            with_payload=True,
            with_vectors=False
        )
        all_points.extend(res)
        if not next_offset:
            break
            
    G = nx.Graph()
    colors = {
        "book": "#a64dff",
        "sthana_index": "#a64dff",
        "chapter": "#ff4d4d",
        "chapter_root": "#ff4d4d",
        "section": "#4da6ff",
        "verse": "#4dff4d",
        "verse_block": "#4dff4d",
        "stub_botanical": "#ffa64d",
        "stub_glossary": "#ffa64d",
        "unknown": "#cccccc"
    }

    print(f"Building graph with {len(all_points)} nodes...")
    for point in all_points:
        payload = point.payload
        node_id = str(point.id)
        level = payload.get("level", "unknown")
        
        G.add_node(node_id, 
                   label=payload.get("title") or payload.get("section_title") or node_id[:8],
                   color=colors.get(level, colors["unknown"]),
                   size=15 if level in ["book", "sthana_index", "chapter"] else 5,
                   treatise=payload.get("source_treatise", "unknown"),
                   level=level)

    for point in all_points:
        payload = point.payload
        node_id = str(point.id)
        parent_id = payload.get("parent_id")
        if parent_id and str(parent_id) in G:
            G.add_edge(str(parent_id), node_id, type="parent")
        next_id = payload.get("next_id")
        if next_id and str(next_id) in G:
            G.add_edge(node_id, str(next_id), type="next")

    print("Calculating layout (spring layout)...")
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
                "level": node_data["level"]
            }
        })
        
    for i, (u, v) in enumerate(G.edges()):
        sigma_data["edges"].append({
            "key": f"e{i}",
            "source": u,
            "target": v,
            "attributes": {"color": "#333333", "size": 1}
        })
    
    cached_graph_data = sigma_data
    return sigma_data

# --- Routes ---

@app.route('/lib/<path:path>')
def send_lib(path):
    return send_from_directory('lib', path)

@app.route("/")
def index():
    graph_json = json.dumps(get_graph_structure())
    
    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Ayurveda LIVE Hybrid View</title>
    <style>
        body { margin: 0; padding: 0; background: #050505; color: white; font-family: 'Segoe UI', sans-serif; overflow: hidden; }
        #container { width: 100vw; height: 100vh; background: radial-gradient(circle, #1a1a1a 0%, #050505 100%); }
        #overlay { position: absolute; top: 20px; left: 20px; background: rgba(0,0,0,0.9); padding: 20px; border-radius: 8px; border: 1px solid #333; z-index: 10; width: 320px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        .section-title { color: #00adf6; font-weight: bold; margin: 15px 0 10px 0; font-size: 14px; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 5px; }
        input[type="text"] { width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #444; background: #111; color: white; box-sizing: border-box; }
        button { width: 100%; margin-top: 10px; padding: 10px; background: #00adf6; border: none; color: white; border-radius: 4px; cursor: pointer; font-weight: bold; }
        button:disabled { background: #444; cursor: not-allowed; }
        #tooltip { position: absolute; display: none; background: rgba(10,10,10,0.95); padding: 12px; border: 1px solid #00adf6; border-radius: 6px; pointer-events: none; z-index: 20; color: #eee; font-size: 13px; box-shadow: 0 0 10px rgba(0, 173, 246, 0.3); }
        .slider-container { margin-top: 15px; }
        input[type="range"] { width: 100%; accent-color: #00adf6; }
        #status { color: #00adf6; font-size: 12px; margin-top: 10px; font-style: italic; }
        #max_score_info { font-size: 11px; color: #ffcc00; margin-top: 5px; font-weight: bold; }
        .badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-left: 5px; background: #333; color: #aaa; }
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="overlay">
        <h3>Ayurveda LIVE Hybrid</h3>
        <p style="font-size:11px; color:#888;">Fusing Double-E5 + SPLADE via RRF</p>
        
        <div class="section-title">Hybrid Search</div>
        <input type="text" id="query_input" placeholder="Search concept (e.g. digestion)">
        <button id="search_btn" onclick="performSearch()">Compute Fusion Heatmap</button>
        <div id="status">Ready.</div>
        <div id="max_score_info"></div>

        <div class="section-title">Fusion Sensitivity</div>
        <div class="slider-container">
            <input type="range" id="threshold" min="0.0" max="1.0" step="0.005" value="0.02" oninput="updateUI()">
            <div style="display:flex; justify-content:space-between; margin-top:5px;">
                <span>Broad</span>
                <span id="threshold_val" style="color:#00adf6; font-weight:bold;">0.02</span>
                <span>Precise</span>
            </div>
        </div>
        <p><small>RRF scores are typically lower than cosine similarity. 0.01-0.05 is standard for broad maps.</small></p>

        <div class="controls" style="margin-top:20px; border-top:1px solid #333; padding-top:10px;">
            <p><small>• Scroll to zoom, Drag to pan</small></p>
            <p><small>• Heatmap: Red (Strong) → Orange (Moderate)</small></p>
        </div>
    </div>
    <div id="tooltip"></div>

    <script src="/lib/sigma/graphology.min.js"></script>
    <script src="/lib/sigma/sigma.min.js"></script>

    <script>
        const graphData = __GRAPH_JSON__;
        let nodeScores = {};
        let currentThreshold = 0.02;
        let renderer;
        let graph;

        function initGraph() {
            const container = document.getElementById("container");
            const GraphConstructor = window.graphology || graphology;
            graph = new GraphConstructor();

            graphData.nodes.forEach(n => graph.addNode(n.key, n.attributes));
            graphData.edges.forEach(e => graph.addEdge(e.source, e.target, e.attributes));

            renderer = new Sigma(graph, container, {
                renderEdgeLabels: false,
                labelColor: { color: "#888" },
                defaultEdgeColor: "#222",
                labelSize: 11,
                minCameraZoom: 0.001
            });

            renderer.setSetting("nodeReducer", (node, data) => {
                const res = { ...data };
                const score = nodeScores[node] || 0;
                
                if (Object.keys(nodeScores).length > 0) {
                    if (score >= currentThreshold) {
                        // RRF scaling is different, we amplify the visual growth
                        const amplification = (score / currentThreshold);
                        res.size = res.size * Math.min(4, amplification);
                        
                        // Heatmap gradient
                        const intensity = Math.min(1.0, (score - currentThreshold) / (0.1 - currentThreshold));
                        res.color = `rgb(255, ${Math.floor(200 * (1 - intensity))}, 0)`;
                        res.zIndex = 1;
                    } else {
                        res.color = "#111";
                        res.label = "";
                        res.zIndex = -1;
                    }
                }
                return res;
            });

            renderer.setSetting("edgeReducer", (edge, data) => {
                const res = { ...data };
                if (Object.keys(nodeScores).length > 0) {
                    const source = graph.source(edge);
                    const target = graph.target(edge);
                    const sScore = nodeScores[source] || 0;
                    const tScore = nodeScores[target] || 0;
                    
                    if (sScore >= currentThreshold && tScore >= currentThreshold) {
                        res.color = "#ffcc00";
                        res.size = 2;
                    } else {
                        res.hidden = true;
                    }
                }
                return res;
            });

            const tooltip = document.getElementById("tooltip");
            renderer.on("enterNode", ({ node }) => {
                const attr = graph.getNodeAttributes(node);
                const score = nodeScores[node];
                if (score && score >= currentThreshold) {
                    tooltip.style.display = "block";
                    tooltip.innerHTML = `<strong>${attr.label}</strong><hr style="border:0;border-top:1px solid #333;margin:8px 0;"><b>Fusion Score:</b> ${score.toFixed(6)}<br><b>Level:</b> ${attr.level}`;
                }
            });
            renderer.on("leaveNode", () => tooltip.style.display = "none");
            window.addEventListener("mousemove", (e) => {
                if (tooltip.style.display === "block") {
                    tooltip.style.left = (e.clientX + 20) + "px";
                    tooltip.style.top = (e.clientY + 20) + "px";
                }
            });
        }

        async function performSearch() {
            const query = document.getElementById("query_input").value;
            const btn = document.getElementById("search_btn");
            const status = document.getElementById("status");
            const maxScoreInfo = document.getElementById("max_score_info");
            if (!query) return;

            btn.disabled = true;
            status.innerText = "Fusion Engine Computing...";

            try {
                const response = await fetch("/search?q=" + encodeURIComponent(query));
                nodeScores = await response.json();
                
                const scores = Object.values(nodeScores);
                if (scores.length > 0) {
                    const maxS = Math.max(...scores);
                    maxScoreInfo.innerText = "Max Fusion Score: " + maxS.toFixed(6);
                    
                    // Auto-adjust threshold if current is too high for RRF
                    if (maxS < currentThreshold) {
                        currentThreshold = Math.max(0.001, maxS / 2);
                        document.getElementById("threshold").value = currentThreshold;
                        document.getElementById("threshold_val").innerText = currentThreshold.toFixed(3);
                    }
                }
                
                status.innerText = "Fused results for " + Object.keys(nodeScores).length + " nodes.";
                renderer.refresh();
            } catch (err) {
                console.error(err);
                status.innerText = "Fusion Error.";
            } finally {
                btn.disabled = false;
            }
        }

        function updateUI() {
            currentThreshold = parseFloat(document.getElementById("threshold").value);
            document.getElementById("threshold_val").innerText = currentThreshold.toFixed(3);
            if (renderer) renderer.refresh();
        }

        window.onload = initGraph;
    </script>
</body>
</html>
"""
    return html_template.replace("__GRAPH_JSON__", graph_json)

@app.route("/search")
def search():
    query = request.args.get("q", "")
    if not query:
        return jsonify({})
    
    print(f"HYBRID DEBUG: Computing for '{query}'...")
    
    # E5 Prefix requirement: "query: " for retrieval
    query_prefix = "query: "

    # 1. Prepare Dense Vectors (Remote)
    # Vector 1: English Semantic
    semantic_vec = dense_model.encode(f"{query_prefix}{query}").tolist()
    
    # Vector 2: Sanskrit Semantic (Translation Bridge)
    normalized_text = _normalize_query(query)
    translit_vec = dense_model.encode(f"{query_prefix}{normalized_text}").tolist()
    
    # 2. Prepare Sparse Vector (Remote - SPLADE via sidecar)
    sparse_dict = dense_model.encode_sparse(normalized_text)
    sparse_vec = models.SparseVector(
        indices=[int(k) for k in sparse_dict.keys()],
        values=[float(v) for v in sparse_dict.values()]
    )

    print(f"DEBUG: Fusing results using RRF on collection '{COLLECTION_NAME}'...")
    try:
        # 3. Triple-Vector Fusion Query
        res = client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                # Semantic English
                models.Prefetch(
                    query=semantic_vec,
                    using="dense_english",
                    limit=100
                ),
                # Transliterated Sanskrit
                models.Prefetch(
                    query=translit_vec,
                    using="dense_sanskrit",
                    limit=100
                ),
                # Keyword Sparse (SPLADE)
                models.Prefetch(
                    query=sparse_vec,
                    using="sparse_splade",
                    limit=100
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=500, # Heatmap candidate size
            with_payload=False
        )
        
        # RRF returns fused scores
        scores = {str(hit.id): float(hit.score) for hit in res.points}
        return jsonify(scores)
    except Exception as e:
        print(f"ERROR: Hybrid fusion failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("\n" + "="*60)
    print("AYURVEDA LIVE HYBRID VISUALIZER (RRF + SPLADE + DENSE)")
    print("="*60)
    print(f"Active Collection: {COLLECTION_NAME}")
    print("1. Ensure Qdrant & GPU Sidecar are running")
    print("2. Open your browser at http://localhost:5000")
    print("="*60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
