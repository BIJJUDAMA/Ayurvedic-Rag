import sys
import os
import json
import networkx as nx
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models
import matplotlib.cm as cm
import matplotlib.colors as mcolors

# Attempt to import community, handle missing dependency gracefully
try:
    import community as community_louvain
except ImportError:
    print("Warning: 'python-louvain' not found. Thematic clustering will be limited.")
    community_louvain = None

# Configuration
COLLECTION_NAME = "ayurveda_rag"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333

def generate_html(sigma_data, num_communities, title, filename, mode):
    """Generates a standalone, optimized HTML file with Samhita and Level toggles."""
    
    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <!-- Use local libraries for offline stability -->
    <script src="lib/sigma/graphology.min.js"></script>
    <script src="lib/sigma/sigma.min.js"></script>
    <style>
        body {{ margin: 0; padding: 0; background: #050505; color: white; font-family: 'Inter', system-ui, sans-serif; overflow: hidden; }}
        #container {{ width: 100vw; height: 100vh; }}
        
        #overlay {{ position: absolute; top: 20px; left: 20px; background: rgba(10,10,10,0.92); padding: 25px; border-radius: 12px; border: 1px solid #333; z-index: 10; width: 320px; max-height: 90vh; overflow-y: auto; backdrop-filter: blur(8px); box-shadow: 0 8px 32px rgba(0,0,0,0.8); }}
        
        h3 {{ margin: 0 0 15px 0; color: #00adf6; font-size: 20px; letter-spacing: -0.5px; }}
        .section-title {{ color: #00adf6; font-weight: 800; margin: 20px 0 10px 0; font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.8; border-bottom: 1px solid #333; padding-bottom: 4px; }}
        
        .filter-row {{ display: flex; align-items: center; margin-bottom: 8px; font-size: 13px; cursor: pointer; user-select: none; }}
        .filter-row:hover {{ color: #00adf6; }}
        input[type="checkbox"] {{ margin-right: 12px; accent-color: #00adf6; width: 16px; height: 16px; cursor: pointer; }}
        .dot {{ width: 12px; height: 12px; border-radius: 4px; margin-right: 10px; flex-shrink: 0; border: 1px solid rgba(255,255,255,0.1); }}
        
        #tooltip {{ position: absolute; display: none; background: rgba(5,5,5,0.95); padding: 15px; border: 1px solid #00adf6; border-radius: 10px; pointer-events: none; z-index: 20; width: 250px; box-shadow: 0 0 20px rgba(0,173,246,0.2); font-size: 13px; }}
        
        .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 15px; padding-top: 15px; border-top: 1px solid #333; }}
        .stat-label {{ font-size: 9px; color: #888; text-transform: uppercase; }}
        .stat-val {{ font-size: 16px; color: #fff; font-weight: 700; }}

        .mode-tag {{ display: inline-block; padding: 2px 8px; background: #333; border-radius: 4px; font-size: 10px; font-weight: bold; text-transform: uppercase; margin-bottom: 10px; color: #888; }}
        
        .controls {{ margin-top: 15px; display: flex; gap: 8px; }}
        .controls button {{ flex: 1; padding: 6px; font-size: 11px; background: #333; border: 1px solid #444; color: white; border-radius: 4px; cursor: pointer; }}

        .performance-note {{ position: absolute; bottom: 20px; right: 20px; font-size: 10px; color: #333; }}
        ::-webkit-scrollbar {{ width: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #333; border-radius: 10px; }}
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="overlay">
        <div class="mode-tag">{mode} VIEW</div>
        <h3>{title}</h3>
        
        <div class="section-title">Treatises</div>
        <div class="filter-row"><input type="checkbox" id="f_charaka" checked onchange="updateFilters()"> Charaka Samhita</div>
        <div class="filter-row"><input type="checkbox" id="f_susruta" checked onchange="updateFilters()"> Susruta Samhita</div>
        <div class="filter-row"><input type="checkbox" id="f_astanga" checked onchange="updateFilters()"> Astanga Hridaya</div>

        <div class="section-title">Hierarchy Levels</div>
        <div class="filter-row"><input type="checkbox" id="l_book" checked onchange="updateFilters()"> <div class="dot" style="background: #ffffff; border-radius: 50%;"></div> Book Root</div>
        <div class="filter-row"><input type="checkbox" id="l_sthana" checked onchange="updateFilters()"> <div class="dot" style="background: #aaaaaa; border: 1px dashed #fff;"></div> Sthana Index</div>
        <div class="filter-row"><input type="checkbox" id="l_chapter" checked onchange="updateFilters()"> <div class="dot" style="background: #ff4d4d"></div> Chapter</div>
        <div class="filter-row"><input type="checkbox" id="l_section" checked onchange="updateFilters()"> <div class="dot" style="background: #ffa64d"></div> Section</div>
        <div class="filter-row"><input type="checkbox" id="l_verse" checked onchange="updateFilters()"> <div class="dot" style="background: #4dff4d"></div> Verse Block</div>
        <div class="filter-row"><input type="checkbox" id="l_glossary" checked onchange="updateFilters()"> <div class="dot" style="background: #4da6ff"></div> Glossary/Botanical</div>

        <div class="controls">
            <button onclick="renderer.getCamera().animatedReset()">Center View</button>
            <button onclick="toggleLabels()">Labels</button>
        </div>

        <div class="section-title">Manuscript Stats</div>
        <div class="stat-grid">
            <div><div class="stat-label">Nodes</div><div class="stat-val" id="node_count">{len(sigma_data['nodes']):,}</div></div>
            <div><div class="stat-label">Engine</div><div class="stat-val">Hierarchy</div></div>
        </div>
        
        <p style="font-size:11px; color:#666; margin-top:20px; line-height:1.4;">
            Visualization of <b>{title}</b> structural relationships.
        </p>
    </div>

    <div id="tooltip"></div>
    <div class="performance-note">WebGL Render Engine • Hierarchical Manuscript Explorer</div>

    <script>
        let renderer;
        let graph;
        let hoveredNode = null;
        let showLabels = true;
        
        const filterState = {{
            treatises: {{
                charak_samhita: true,
                shusrut_samhita: true,
                astanga_hridaya: true
            }},
            levels: {{
                book: true,
                sthana_index: true,
                chapter: true,
                chapter_root: true,
                section: true,
                verse: true,
                verse_block: true,
                stub_botanical: true,
                stub_glossary: true
            }}
        }};

        function updateFilters() {{
            filterState.treatises.charak_samhita = document.getElementById("f_charaka").checked;
            filterState.treatises.shusrut_samhita = document.getElementById("f_susruta").checked;
            filterState.treatises.astanga_hridaya = document.getElementById("f_astanga").checked;

            filterState.levels.book = document.getElementById("l_book").checked;
            filterState.levels.sthana_index = document.getElementById("l_sthana").checked;
            filterState.levels.chapter = document.getElementById("l_chapter").checked;
            filterState.levels.chapter_root = document.getElementById("l_chapter").checked;
            filterState.levels.section = document.getElementById("l_section").checked;
            filterState.levels.verse = document.getElementById("l_verse").checked;
            filterState.levels.verse_block = document.getElementById("l_verse").checked;
            filterState.levels.stub_botanical = document.getElementById("l_glossary").checked;
            filterState.levels.stub_glossary = document.getElementById("l_glossary").checked;

            renderer.refresh();
        }}

        function toggleLabels() {{
            showLabels = !showLabels;
            renderer.refresh();
        }}

        try {{
            const data = {json.dumps(sigma_data)};
            
            // Robust Graphology Initialization for local minified bundle
            let GraphConstructor;
            if (window.graphology && window.graphology.Graph) {{
                GraphConstructor = window.graphology.Graph;
            }} else if (window.graphology && typeof window.graphology === 'function') {{
                GraphConstructor = window.graphology;
            }} else if (typeof Graph !== 'undefined') {{
                GraphConstructor = Graph;
            }} else {{
                throw new Error("Graphology library not loaded correctly. Please check your internet connection or CDN status.");
            }}

            graph = new GraphConstructor();

            data.nodes.forEach(n => graph.addNode(n.key, n.attributes));
            data.edges.forEach(e => graph.addEdge(e.source, e.target, e.attributes));

            renderer = new Sigma(graph, document.getElementById("container"), {{
                labelRenderedSizeThreshold: 8,
                minCameraZoom: 0.001,
                maxCameraZoom: 50,
                defaultEdgeColor: "#222",
                labelColor: {{ color: "#ccc" }},
                labelSize: 12
            }});

            renderer.setSetting("nodeReducer", (node, data) => {{
                const res = {{ ...data }};
                
                // Visibility Checks
                if (data.treatise && filterState.treatises[data.treatise] === false) {{ res.hidden = true; return res; }}
                if (data.level && filterState.levels[data.level] === false) {{ res.hidden = true; return res; }}
                
                if (!showLabels) res.label = "";

                return res;
            }});

            renderer.setSetting("edgeReducer", (edge, data) => {{
                const res = {{ ...data }};
                const source = graph.source(edge);
                const target = graph.target(edge);
                const sourceData = graph.getNodeAttributes(source);
                const targetData = graph.getNodeAttributes(target);

                if (filterState.treatises[sourceData.treatise] === false || filterState.levels[sourceData.level] === false ||
                    filterState.treatises[targetData.treatise] === false || filterState.levels[targetData.level] === false) {{
                    res.hidden = true;
                    return res;
                }}

                return res;
            }});

            renderer.on("enterNode", ({{ node }}) => {{
                hoveredNode = node;
                const attr = graph.getNodeAttributes(node);
                tooltip.style.display = "block";
                tooltip.innerHTML = `
                    <div style="font-weight:800; color:#00adf6; margin-bottom:5px;">${{attr.label}}</div>
                    <div style="font-size:11px; opacity:0.6;">${{attr.treatise}} • ${{attr.level}}</div>
                `;
                renderer.refresh();
            }});

            renderer.on("leaveNode", () => {{ hoveredNode = null; tooltip.style.display = "none"; renderer.refresh(); }});
            window.addEventListener("mousemove", (e) => {{
                if (tooltip.style.display === "block") {{
                    tooltip.style.left = (e.clientX + 15) + "px";
                    tooltip.style.top = (e.clientY + 15) + "px";
                }}
            }});
            
            // Auto-center after a short delay to allow renderer to settle
            setTimeout(() => renderer.getCamera().animatedReset(), 500);

        }} catch (err) {{ 
            console.error(err); 
            alert("Visualization Error: " + err.message);
        }}
    </script>
</body>
</html>
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_template)

def main():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    try:
        client.get_collection(COLLECTION_NAME)
    except Exception:
        print(f"Error: Collection '{COLLECTION_NAME}' not found.")
        return

    print("Fetching points from Qdrant...")
    all_points = []
    res, next_offset = client.scroll(collection_name=COLLECTION_NAME, limit=1000, with_payload=True)
    all_points.extend(res)
    while next_offset:
        res, next_offset = client.scroll(collection_name=COLLECTION_NAME, limit=1000, offset=next_offset, with_payload=True)
        all_points.extend(res)

    if not all_points:
        print("Error: No points found in collection.")
        return

    G = nx.Graph()
    
    # Level UI Colors (Primary)
    ui_colors = {
        "book": "#ffffff", 
        "sthana_index": "#aaaaaa", 
        "chapter": "#ff4d4d", 
        "chapter_root": "#ff4d4d",
        "section": "#ffa64d", 
        "verse": "#4dff4d", 
        "verse_block": "#4dff4d",
        "stub_botanical": "#4da6ff", 
        "stub_glossary": "#4da6ff"
    }

    print(f"Building graph with {len(all_points)} nodes...")
    for p in all_points:
        node_id = str(p.id)
        payload = p.payload
        source = payload.get("source", "unknown")
        level = payload.get("level", "unknown")
        
        label = payload.get("section_title") or payload.get("title") or node_id[:8]
        if len(label) > 40: label = label[:37] + "..."
        
        G.add_node(node_id, 
                   label=label,
                   treatise=source,
                   level=level,
                   ui_color=ui_colors.get(level, "#666666"))

    # Edges
    for p in all_points:
        node_id = str(p.id)
        parent_id = p.payload.get("parent_id")
        if parent_id and str(parent_id) in G: G.add_edge(str(parent_id), node_id, type="parent")
        next_id = p.payload.get("next_id")
        if next_id and str(next_id) in G: G.add_edge(node_id, str(next_id), type="sequential")
        related = p.payload.get("metadata", {}).get("related_nodes", [])
        for r in related:
            if str(r) in G: G.add_edge(node_id, str(r), type="semantic")

    print("Performing Graph Analytics...")
    centrality = nx.degree_centrality(G)
    communities = {n: 0 for n in G.nodes()}
    num_communities = 1
    if community_louvain:
        communities = community_louvain.best_partition(G)
        num_communities = max(communities.values()) + 1
    cmap = cm.get_cmap('tab20', num_communities)

    # 1. TREATISE VIEW
    print("Generating Treatise View...")
    pos_t = nx.spring_layout(G, k=0.15, iterations=50, seed=42)
    
    # Normalize coordinates to center them (Sigma.js v2 is sensitive to this)
    all_pos = np.array(list(pos_t.values()))
    center = np.mean(all_pos, axis=0)
    pos_t = {n: (pos_t[n] - center) * 2000 for n in G.nodes()}

    nodes_t = []
    for n in G.nodes():
        attr = G.nodes[n]
        nodes_t.append({"key": n, "attributes": {
            **attr, "x": float(pos_t[n][0]), "y": float(pos_t[n][1]), 
            "color": attr["ui_color"], 
            "size": 5 + centrality[n]*800, "centrality": round(centrality[n], 4)
        }})
    generate_html({"nodes": nodes_t, "edges": [{"source": u, "target": v, "attributes": {"color": "#222"}} for u,v in G.edges()]}, 
                  num_communities, "Ayurveda Treatise Explorer", "visualize_ayurveda_treatise.html", "treatise")

    print("\n[SUCCESS] Dashboard ready. Interaction simplified.")

if __name__ == "__main__":
    main()
