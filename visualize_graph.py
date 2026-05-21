import sys
import os

# 1. Add project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import json
import networkx as nx
from qdrant_client import QdrantClient

# Configuration
COLLECTION_NAME = "ayurveda_rag"

def visualize_qdrant_graph(collection_name: str, output_file: str = "visualize_ayurveda_unified.html"):
    client = QdrantClient(host="localhost", port=6333)
    
    if not client.collection_exists(collection_name):
        print(f"Error: Collection '{collection_name}' does not exist.")
        return

    print(f"Fetching ALL points from collection '{collection_name}'...")
    
    # Fetch ALL points using scrolling
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
            
    G = nx.Graph() # Use undirected for layout calculation to pull clusters better
    
    # Mapping for different levels
    colors = {
        "book": "#a64dff",              # Purple (Root)
        "sthana_index": "#a64dff",      # Purple
        "chapter": "#ff4d4d",           # Red
        "chapter_root": "#ff4d4d",      # Red
        "section": "#4da6ff",           # Blue
        "verse": "#4dff4d",             # Green
        "verse_block": "#4dff4d",       # Green
        "stub_botanical": "#ffa64d",    # Orange
        "stub_glossary": "#ffa64d",     # Orange
        "unknown": "#cccccc"
    }

    print(f"Building graph with {len(all_points)} nodes...")

    # First pass: Add all nodes
    for point in all_points:
        payload = point.payload
        node_id = str(point.id)

        # Determine Label
        label = (
            payload.get("section_title") or 
            payload.get("chapter_title") or 
            payload.get("title") or 
            node_id[:8]
        )

        # Determine Type and Color
        level = payload.get("level", "unknown")
        color = colors.get(level, colors["unknown"])
        source = payload.get("source_treatise", "unknown")

        G.add_node(node_id, 
                   label=str(label), 
                   color=color,
                   size=15 if level in ["book", "sthana_index", "chapter"] else 5,
                   treatise=source,
                   level=level)

    # Second pass: Add edges
    for point in all_points:
        payload = point.payload
        node_id = str(point.id)
        
        # 1. Hierarchical (parent_id)
        parent_id = payload.get("parent_id")
        if parent_id and str(parent_id) in G:
            G.add_edge(str(parent_id), node_id, type="parent")
            
        # 2. Sequential (next_id)
        next_id = payload.get("next_id")
        if next_id and str(next_id) in G:
            G.add_edge(node_id, str(next_id), type="next")

    print("Calculating layout (this may take a minute)...")
    # Pre-compute positions using spring layout
    pos = nx.spring_layout(G, k=0.15, iterations=50, seed=42)
    
    # Prepare data for Sigma.js
    sigma_data = {
        "nodes": [],
        "edges": []
    }
    
    for node_id in G.nodes():
        node_data = G.nodes[node_id]
        x, y = pos[node_id]
        sigma_data["nodes"].append({
            "key": node_id,
            "attributes": {
                "x": float(x * 2000), # Scaling for visibility
                "y": float(y * 2000),
                "label": node_data["label"],
                "color": node_data["color"],
                "size": node_data["size"],
                "treatise": node_data["treatise"],
                "level": node_data["level"]
            }
        })
        
    for i, (u, v) in enumerate(G.edges()):
        edge_type = G.edges[u, v].get("type", "unknown")
        sigma_data["edges"].append({
            "key": f"e{i}",
            "source": u,
            "target": v,
            "attributes": {
                "color": "#666666" if edge_type == "parent" else "#999999",
                "size": 1
            }
        })

    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Ayurveda Unified Knowledge Graph (WebGL)</title>
    <style>
        body {{ margin: 0; padding: 0; background: #050505; color: white; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; overflow: hidden; }}
        #container {{ width: 100vw; height: 100vh; background: radial-gradient(circle, #1a1a1a 0%, #050505 100%); }}
        
        #overlay {{ position: absolute; top: 20px; left: 20px; background: rgba(0,0,0,0.85); padding: 20px; border-radius: 8px; border: 1px solid #333; z-index: 10; box-shadow: 0 4px 15px rgba(0,0,0,0.5); width: 250px; pointer-events: auto; }}
        
        .section-title {{ color: #00adf6; font-weight: bold; margin: 15px 0 10px 0; font-size: 14px; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 5px; }}
        .legend {{ display: flex; align-items: center; margin-bottom: 8px; font-size: 13px; cursor: pointer; }}
        .legend:hover {{ background: rgba(255,255,255,0.1); }}
        .dot {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 10px; border: 1px solid rgba(255,255,255,0.2); flex-shrink: 0; }}
        
        .toggle-row {{ display: flex; align-items: center; margin-bottom: 8px; font-size: 13px; }}
        input[type="checkbox"] {{ margin-right: 10px; cursor: pointer; accent-color: #00adf6; }}
        
        #tooltip {{ position: absolute; display: none; background: rgba(10,10,10,0.95); padding: 12px; border: 1px solid #00adf6; border-radius: 6px; pointer-events: none; z-index: 20; color: #eee; font-size: 13px; line-height: 1.5; box-shadow: 0 0 10px rgba(0, 173, 246, 0.3); }}
        #status {{ color: #00adf6; font-weight: bold; margin-bottom: 15px; font-size: 14px; }}
        h3 {{ margin: 0 0 5px 0; color: #00adf6; font-size: 18px; letter-spacing: 1px; }}
        p {{ margin: 5px 0; font-size: 12px; color: #888; }}
        
        .controls {{ margin-top: 15px; padding-top: 10px; border-top: 1px solid #333; }}
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="overlay">
        <h3>Ayurveda Unified Graph</h3>
        <div id="status">Initializing...</div>
        
        <div class="section-title">Treatises</div>
        <div class="toggle-row"><input type="checkbox" id="charaka" checked onchange="updateFilters()"> <label for="charaka">Charaka Samhita</label></div>
        <div class="toggle-row"><input type="checkbox" id="susruta" checked onchange="updateFilters()"> <label for="susruta">Susruta Samhita</label></div>
        <div class="toggle-row"><input type="checkbox" id="astanga" checked onchange="updateFilters()"> <label for="astanga">Astanga Hridaya</label></div>

        <div class="section-title">Hierarchy Levels</div>
        <div class="legend"><input type="checkbox" id="lvl_book" checked onchange="updateFilters()"> <div class="dot" style="background: #a64dff"></div> Book Root</div>
        <div class="legend"><input type="checkbox" id="lvl_sthana" checked onchange="updateFilters()"> <div class="dot" style="background: #a64dff; border-style: dashed;"></div> Sthana Index</div>
        <div class="legend"><input type="checkbox" id="lvl_chapter" checked onchange="updateFilters()"> <div class="dot" style="background: #ff4d4d"></div> Chapter</div>
        <div class="legend"><input type="checkbox" id="lvl_section" checked onchange="updateFilters()"> <div class="dot" style="background: #4da6ff"></div> Section</div>
        <div class="legend"><input type="checkbox" id="lvl_verse" checked onchange="updateFilters()"> <div class="dot" style="background: #4dff4d"></div> Verse Block</div>

        <div class="section-title">Clinical Pathfinder</div>
        <div class="toggle-row">
            <input type="text" id="path_search" placeholder="Search disease (e.g. Jwara)" style="width:100%; padding:5px; border-radius:4px; border:1px solid #333; background:#222; color:white;">
        </div>
        <button onclick="findClinicalPath()" style="width:100%; margin-top:5px; padding:5px; background:#00adf6; border:none; color:white; border-radius:4px; cursor:pointer;">Highlight Path</button>
        <button onclick="clearPath()" style="width:100%; margin-top:5px; padding:5px; background:#444; border:none; color:white; border-radius:4px; cursor:pointer;">Clear</button>

        <div class="controls">
            <p><small>• Scroll to zoom</small></p>
            <p><small>• Drag to pan</small></p>
            <p><small>• Hover for details</small></p>
        </div>
    </div>
    <div id="tooltip"></div>

    <script src="lib/sigma/graphology.min.js"></script>
    <script src="lib/sigma/sigma.min.js"></script>

    <script>
        const statusEl = document.getElementById("status");
        let renderer;
        let graph;

        const filters = {{
            treatises: {{
                charak_samhita: true,
                shusrut_samhita: true,
                astanga_hridaya: true
            }},
            levels: {{
                book: true,
                sthana_index: true,
                chapter_root: true,
                chapter: true,
                section: true,
                verse_block: true,
                verse: true,
                stub_botanical: true,
                stub_glossary: true
            }}
        }};

        function updateFilters() {{
            filters.treatises.charak_samhita = document.getElementById("charaka").checked;
            filters.treatises.shusrut_samhita = document.getElementById("susruta").checked;
            filters.treatises.astanga_hridaya = document.getElementById("astanga").checked;
            
            filters.levels.book = document.getElementById("lvl_book").checked;
            filters.levels.sthana_index = document.getElementById("lvl_sthana").checked;
            filters.levels.chapter = document.getElementById("lvl_chapter").checked;
            filters.levels.chapter_root = document.getElementById("lvl_chapter").checked;
            filters.levels.section = document.getElementById("lvl_section").checked;
            filters.levels.verse_block = document.getElementById("lvl_verse").checked;
            filters.levels.verse = document.getElementById("lvl_verse").checked;
            
            renderer.refresh();
        }}
        
        let highlightedNodes = new Set();

        function findClinicalPath() {{
            const search = document.getElementById("path_search").value.toLowerCase();
            if (!search) return;
            
            clearPath();
            
            graph.forEachNode((node, attr) => {{
                const label = attr.label.toLowerCase();
                const isMatch = label.includes(search);
                const isPathway = label.includes("nidana") || label.includes("rupa") || label.includes("samprapti") || label.includes("chikitsa");
                
                if (isMatch || (highlightedNodes.size > 0 && isPathway)) {{
                    highlightedNodes.add(node);
                }}
            }});

            // Refresh renderer to apply highlighting
            renderer.refresh();
            statusEl.innerText = "Path Highlighted (" + highlightedNodes.size + " nodes)";
        }}

        function clearPath() {{
            highlightedNodes.clear();
            renderer.refresh();
            statusEl.innerText = "GPU Active (" + graph.order + " nodes)";
        }}

        try {{
            const data = {json.dumps(sigma_data)};
            const container = document.getElementById("container");
            
            const GraphConstructor = window.graphology || graphology;
            graph = new GraphConstructor();

            data.nodes.forEach(n => graph.addNode(n.key, n.attributes));
            data.edges.forEach(e => graph.addEdge(e.source, e.target, e.attributes));

            renderer = new Sigma(graph, container, {{
                renderEdgeLabels: false,
                labelColor: {{ color: "#888" }},
                defaultEdgeColor: "#222",
                labelSize: 11,
                labelWeight: "300",
                minCameraZoom: 0.001,
                maxCameraZoom: 20
            }});

            // REDUCERS for high-performance toggling and highlighting
            renderer.setSetting("nodeReducer", (node, data) => {{
                const res = {{ ...data }};
                
                // Hide if treatise/level filter is active
                const isTreatiseHidden = !filters.treatises[data.treatise];
                const isLevelHidden = !filters.levels[data.level];
                
                if (isTreatiseHidden || isLevelHidden) {{
                    res.hidden = true;
                    res.label = "";
                    return res;
                }}

                // Apply Pathfinder Highlighting
                if (highlightedNodes.size > 0) {{
                    if (highlightedNodes.has(node)) {{
                        res.size = res.size * 2;
                        res.zIndex = 1;
                    }} else {{
                        res.color = "#111";
                        res.label = "";
                        res.zIndex = -1;
                    }}
                }}
                
                return res;
            }});

            renderer.setSetting("edgeReducer", (edge, data) => {{
                const res = {{ ...data }};
                const source = graph.source(edge);
                const target = graph.target(edge);
                const sourceData = graph.getNodeAttributes(source);
                const targetData = graph.getNodeAttributes(target);
                
                if (
                    !filters.treatises[sourceData.treatise] || !filters.levels[sourceData.level] ||
                    !filters.treatises[targetData.treatise] || !filters.levels[targetData.level]
                ) {{
                    res.hidden = true;
                    return res;
                }}

                // Pathway highlighting
                if (highlightedNodes.size > 0) {{
                    if (highlightedNodes.has(source) && highlightedNodes.has(target)) {{
                        res.color = "#00adf6";
                        res.size = 2;
                    }} else {{
                        res.hidden = true;
                    }}
                }}
                
                return res;
            }});

            statusEl.innerText = "GPU Active (" + data.nodes.length + " nodes)";

            // Tooltip logic
            const tooltip = document.getElementById("tooltip");
            renderer.on("enterNode", ({{ node }}) => {{
                const attr = graph.getNodeAttributes(node);
                tooltip.style.display = "block";
                tooltip.innerHTML = `<strong style="color:#00adf6;font-size:15px;">${{attr.label}}</strong><hr style="border:0;border-top:1px solid #333;margin:8px 0;"><b>Treatise:</b> ${{attr.treatise}}<br><b>Level:</b> ${{attr.level}}<br><b>ID:</b> <small>${{node}}</small>`;
            }});

            renderer.on("leaveNode", () => {{
                tooltip.style.display = "none";
            }});

            window.addEventListener("mousemove", (e) => {{
                if (tooltip.style.display === "block") {{
                    tooltip.style.left = (e.clientX + 20) + "px";
                    tooltip.style.top = (e.clientY + 20) + "px";
                }}
            }});

        }} catch (err) {{
            console.error(err);
            statusEl.innerText = "Error: Check Console";
        }}
    </script>
</body>
</html>
"""

    print(f"Saving high-performance visualization to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Done! Open '{output_file}' in your browser for instant, GPU-accelerated viewing.")

if __name__ == "__main__":
    visualize_qdrant_graph(COLLECTION_NAME, "visualize_ayurveda_unified.html")
