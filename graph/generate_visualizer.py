import csv
import json
import math
import random
from pathlib import Path

# File paths
GRAPH_DIR = Path(__file__).parent
DATA_DIR = GRAPH_DIR / "data"
NODES_CSV = DATA_DIR / "graph_nodes.csv"
EDGES_CSV = DATA_DIR / "graph_edges.csv"
OUTPUT_HTML = GRAPH_DIR / "visualizer.html"

def main():
    print("Reading node dataset...")
    nodes = []
    with open(NODES_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if not row:
                continue
            node_id, label, name, attributes_str = row
            try:
                attributes = json.loads(attributes_str) if attributes_str else {}
            except Exception:
                attributes = {}
            nodes.append({
                "id": node_id,
                "label": label,
                "name": name,
                "attributes": attributes
            })

    print(f"Loaded {len(nodes)} nodes.")

    print("Reading edge dataset...")
    edges = []
    with open(EDGES_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if not row:
                continue
            source, target, relationship, properties_str = row
            try:
                properties = json.loads(properties_str) if properties_str else {}
            except Exception:
                properties = {}
            
            # CRITICAL CORRECTION: Map INGREDIENT_OF targets to the scientific plant names
            # because the graph_edges.csv target holds commercial names while Plant node IDs use scientific names.
            if relationship == "INGREDIENT_OF":
                mapped_target = properties.get("pharmacopoeia_ref")
                if mapped_target:
                    target = mapped_target

            edges.append({
                "source": source,
                "target": target,
                "relationship": relationship,
                "properties": properties
            })

    print(f"Loaded {len(edges)} edges.")

    # Sort and shuffle categories to build a beautiful structured layout (Galaxy Starburst)
    formulations = [n for n in nodes if n["label"] == "Formulation"]
    plants = [n for n in nodes if n["label"] == "Plant"]
    diseases = [n for n in nodes if n["label"] == "Disease"]

    random.seed(42)
    random.shuffle(formulations)
    random.shuffle(plants)
    random.shuffle(diseases)

    print("Calculating WebGL precomputed positions...")
    
    # 1. Formulations: Galaxy Center Core (dense spiral)
    N_f = len(formulations)
    for i, node in enumerate(formulations):
        theta = (i / max(1, N_f)) * 8 * math.pi
        r = 15 + 65 * (i / max(1, N_f))
        node["x"] = r * math.cos(theta)
        node["y"] = r * math.sin(theta)
        node["color"] = "#ff4757" # Coral/Red
        node["size"] = 7.5

    # 2. Plants: Middle Spiral Arms
    N_p = len(plants)
    for i, node in enumerate(plants):
        arm = i % 3  # 3 spiral arms
        theta = (i / max(1, N_p)) * 24 * math.pi + (arm * 2 * math.pi / 3)
        r = 130 + 170 * (i / max(1, N_p))
        node["x"] = r * math.cos(theta) + random.uniform(-8, 8)
        node["y"] = r * math.sin(theta) + random.uniform(-8, 8)
        node["color"] = "#2ed573" # Emerald/Green
        node["size"] = 4.0

    # 3. Diseases: Outer Expanding Cloud
    N_d = len(diseases)
    for i, node in enumerate(diseases):
        arm = i % 5  # 5 spiral arms
        theta = (i / max(1, N_d)) * 40 * math.pi + (arm * 2 * math.pi / 5)
        r = 350 + 250 * (i / max(1, N_d))
        node["x"] = r * math.cos(theta) + random.uniform(-15, 15)
        node["y"] = r * math.sin(theta) + random.uniform(-15, 15)
        node["color"] = "#1e90ff" # Dodger/Blue
        node["size"] = 2.5

    # Prepare data for Javascript serialization
    js_nodes = json.dumps(nodes, ensure_ascii=False)
    js_edges = json.dumps(edges, ensure_ascii=False)

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GRAYU Knowledge Graph Galaxy Visualizer</title>
  
  <!-- Local Library Dependencies -->
  <script src="lib/sigma/graphology.min.js"></script>
  <script src="lib/sigma/sigma.min.js"></script>
  <script src="lib/tom-select/tom-select.complete.min.js"></script>
  <link rel="stylesheet" href="lib/tom-select/tom-select.css">
  
  <style>
    :root {{
      --bg-color: #0b0f19;
      --panel-bg: rgba(17, 24, 39, 0.95);
      --border-color: rgba(255, 255, 255, 0.08);
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --primary-color: #3b82f6;
      --color-formulation: #ff4757;
      --color-plant: #2ed573;
      --color-disease: #1e90ff;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}

    body {{
      background-color: var(--bg-color);
      color: var(--text-main);
      overflow: hidden;
      width: 100vw;
      height: 100vh;
    }}

    #sigma-container {{
      width: 100%;
      height: 100%;
      position: absolute;
      top: 0;
      left: 0;
      z-index: 1;
    }}

    /* Controls Panel */
    .controls-panel {{
      position: absolute;
      top: 20px;
      left: 20px;
      z-index: 10;
      background: var(--panel-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 18px;
      width: 320px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
      backdrop-filter: blur(10px);
    }}

    .controls-panel h1 {{
      font-size: 1.15rem;
      font-weight: 700;
      margin-bottom: 6px;
      letter-spacing: -0.025em;
      background: linear-gradient(135deg, #60a5fa, #3b82f6);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .controls-panel .subtitle {{
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-bottom: 16px;
    }}

    /* Search Dropdown Override for dark theme */
    .tom-select-wrapper {{
      margin-bottom: 16px;
    }}

    .ts-control {{
      background: rgba(31, 41, 55, 0.7) !important;
      color: var(--text-main) !important;
      border: 1px solid var(--border-color) !important;
      border-radius: 8px !important;
      padding: 10px !important;
      font-size: 0.85rem !important;
    }}

    .ts-dropdown {{
      background: #111827 !important;
      color: var(--text-main) !important;
      border: 1px solid var(--border-color) !important;
      border-radius: 8px !important;
    }}

    .ts-dropdown .active {{
      background: var(--primary-color) !important;
      color: white !important;
    }}

    .ts-dropdown .option {{
      padding: 8px 12px !important;
      font-size: 0.85rem !important;
    }}

    /* Legend Styling */
    .legend {{
      border-top: 1px solid var(--border-color);
      padding-top: 12px;
      margin-top: 12px;
    }}

    .legend-title {{
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 8px;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      margin-bottom: 6px;
      font-size: 0.8rem;
    }}

    .legend-color {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 8px;
    }}

    /* Dynamic Info Sliding Panel */
    #info-panel {{
      position: absolute;
      top: 20px;
      right: -360px;
      width: 340px;
      max-height: calc(100vh - 40px);
      z-index: 10;
      background: var(--panel-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
      backdrop-filter: blur(10px);
      transition: right 0.4s cubic-bezier(0.16, 1, 0.3, 1);
      overflow-y: auto;
    }}

    #info-panel.open {{
      right: 20px;
    }}

    .close-btn {{
      position: absolute;
      top: 15px;
      right: 15px;
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 1.2rem;
      cursor: pointer;
      line-height: 1;
    }}

    .close-btn:hover {{
      color: var(--text-main);
    }}

    .badge {{
      display: inline-block;
      padding: 3px 8px;
      font-size: 0.7rem;
      font-weight: 700;
      border-radius: 4px;
      text-transform: uppercase;
      margin-bottom: 8px;
      letter-spacing: 0.05em;
    }}

    .badge-formulation {{ background: rgba(255, 71, 87, 0.2); color: var(--color-formulation); }}
    .badge-plant {{ background: rgba(46, 213, 115, 0.2); color: var(--color-plant); }}
    .badge-disease {{ background: rgba(30, 144, 255, 0.2); color: var(--color-disease); }}

    .entity-title {{
      font-size: 1.25rem;
      font-weight: 700;
      margin-bottom: 12px;
      line-height: 1.2;
    }}

    .props-group {{
      margin-bottom: 16px;
    }}

    .prop-label {{
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-bottom: 4px;
      font-weight: 600;
      text-transform: uppercase;
    }}

    .prop-value {{
      font-size: 0.85rem;
      line-height: 1.4;
      background: rgba(255, 255, 255, 0.03);
      padding: 8px;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }}

    .neighbors-section {{
      border-top: 1px solid var(--border-color);
      padding-top: 16px;
      margin-top: 16px;
    }}

    .neighbors-title {{
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--text-muted);
      margin-bottom: 8px;
      text-transform: uppercase;
    }}

    .neighbors-list {{
      list-style: none;
      max-height: 200px;
      overflow-y: auto;
    }}

    .neighbors-list li {{
      font-size: 0.8rem;
      padding: 6px 8px;
      background: rgba(255, 255, 255, 0.03);
      border-radius: 4px;
      margin-bottom: 4px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: background 0.2s;
    }}

    .neighbors-list li:hover {{
      background: rgba(255, 255, 255, 0.08);
    }}

    .rel-badge {{
      font-size: 0.65rem;
      font-weight: 600;
      padding: 2px 5px;
      border-radius: 3px;
      background: rgba(255,255,255,0.1);
    }}

    /* Floating Camera Reset Control */
    .camera-control {{
      position: absolute;
      bottom: 20px;
      left: 20px;
      z-index: 10;
      background: var(--panel-bg);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      display: flex;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }}

    .camera-btn {{
      padding: 10px 14px;
      border: none;
      background: none;
      color: var(--text-main);
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 600;
      transition: background 0.2s;
    }}

    .camera-btn:hover {{
      background: rgba(255, 255, 255, 0.06);
    }}

    .camera-btn:not(:last-child) {{
      border-right: 1px solid var(--border-color);
    }}
  </style>
</head>
<body>

  <!-- Sigma WebGL Rendering target container -->
  <div id="sigma-container"></div>

  <!-- Search and Controls Panel -->
  <div class="controls-panel">
    <h1>GRAYU Graph Galaxy</h1>
    <div class="subtitle">WebGL-Powered Interactive Visualizer</div>
    
    <div class="tom-select-wrapper">
      <select id="search-input"></select>
    </div>

    <div class="legend">
      <div class="legend-title">Legend (Double click nodes to focus)</div>
      <div class="legend-item">
        <div class="legend-color" style="background: var(--color-formulation);"></div>
        <span>Formulation ({len(formulations)})</span>
      </div>
      <div class="legend-item">
        <div class="legend-color" style="background: var(--color-plant);"></div>
        <span>Plant ({len(plants)})</span>
      </div>
      <div class="legend-item">
        <div class="legend-color" style="background: var(--color-disease);"></div>
        <span>Disease ({len(diseases)})</span>
      </div>
    </div>
  </div>

  <!-- Dynamic Detail Inspector Side Panel -->
  <div id="info-panel">
    <button class="close-btn" onclick="deselectNode()">&times;</button>
    <div id="info-content"></div>
  </div>

  <!-- Camera Controls -->
  <div class="camera-control">
    <button class="camera-btn" onclick="zoomIn()">+</button>
    <button class="camera-btn" onclick="zoomOut()">-</button>
    <button class="camera-btn" onclick="resetCamera()">Reset view</button>
  </div>

  <script>
    // Embedded Knowledge Graph Dataset from Python CSVs
    const nodesData = {js_nodes};
    const edgesData = {js_edges};

    // Instantiate Graphology Graph Structure
    const graph = new graphology.Graph();

    console.log("Loading nodes into Graphology...");
    nodesData.forEach(node => {{
      graph.addNode(node.id, {{
        label: node.name,
        x: node.x,
        y: node.y,
        size: node.size,
        color: node.color,
        category: node.label,
        attributes: node.attributes
      }});
    }});

    console.log("Loading edges into Graphology...");
    edgesData.forEach((edge, idx) => {{
      // Safeguard against missing endpoints
      if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {{
        // Prevent duplicate edge errors by skipping duplicates
        if (!graph.hasEdge(edge.source, edge.target)) {{
          graph.addEdge(edge.source, edge.target, {{
            type: 'line',
            label: edge.relationship,
            // Color coding for relationships
            color: edge.relationship === 'INGREDIENT_OF' ? '#2ed573' : (edge.relationship === 'ASSOCIATED_WITH' ? '#ffa500' : '#1e90ff'),
            size: 1.0,
            properties: edge.properties
          }});
        }}
      }}
    }});

    // Initialize Sigma.js WebGL Renderer
    const container = document.getElementById("sigma-container");
    const renderer = new Sigma(graph, container, {{
      allowCameraRotation: false,
      renderEdgeLabels: false,
      labelFont: "Arial",
      labelWeight: "600",
      labelColor: {{ color: "#f3f4f6" }}
    }});

    const camera = renderer.getCamera();

    // Interaction State Management
    let selectedNode = null;
    let highlightedNodes = new Set();
    let highlightedEdges = new Set();

    // WebGL rendering filter functions
    renderer.setSetting("nodeReducer", (node, data) => {{
      const res = {{ ...data }};
      
      if (selectedNode) {{
        if (highlightedNodes.has(node)) {{
          res.label = graph.getNodeAttribute(node, "label");
          if (node === selectedNode) {{
            res.size = data.size * 1.5;
          }}
        }} else {{
          // Fade out nodes not connected to focused selection
          res.color = "rgba(44, 62, 80, 0.2)";
          res.label = "";
          res.size = data.size * 0.4;
        }}
      }}
      return res;
    }});

    renderer.setSetting("edgeReducer", (edge, data) => {{
      const res = {{ ...data }};
      
      if (selectedNode) {{
        if (highlightedEdges.has(edge)) {{
          res.size = 2.0;
        }} else {{
          // Fade out edges not connected to selection
          res.color = "rgba(44, 62, 80, 0.05)";
        }}
      }}
      return res;
    }});

    // Setup searchable search interface
    const searchSelect = document.getElementById("search-input");
    
    // Sort nodes alphabetically for clear listing
    const sortedNodes = [...nodesData].sort((a, b) => a.name.localeCompare(b.name));
    
    // Add empty option
    const emptyOpt = document.createElement("option");
    emptyOpt.value = "";
    emptyOpt.text = "";
    searchSelect.appendChild(emptyOpt);

    sortedNodes.forEach(node => {{
      const opt = document.createElement("option");
      opt.value = node.id;
      opt.text = `${{node.name}} (${{node.label}})`;
      searchSelect.appendChild(opt);
    }});

    const tomSelectInstance = new TomSelect("#search-input", {{
      create: false,
      maxItems: 1,
      placeholder: "Search Formulation, Plant, or Disease...",
      onChange: function(value) {{
        if (value) {{
          focusNode(value);
        }} else {{
          deselectNode();
        }}
      }}
    }});

    // Node focusing & neighborhood highlight engine
    function focusNode(nodeId) {{
      if (!graph.hasNode(nodeId)) return;

      selectedNode = nodeId;
      highlightedNodes.clear();
      highlightedEdges.clear();

      highlightedNodes.add(nodeId);

      // Collect immediate neighbors and edges
      graph.forEachNeighbor(nodeId, neighbor => {{
        highlightedNodes.add(neighbor);
      }});

      graph.forEachEdge(nodeId, (edge, attributes, source, target) => {{
        highlightedEdges.add(edge);
      }});

      renderer.refresh();

      // Smooth camera pan & zoom
      const nodePos = renderer.getNodeDisplayData(nodeId);
      camera.animate({{
        x: nodePos.x,
        y: nodePos.y,
        ratio: 0.15
      }}, {{ duration: 700 }});

      // Show info Sidebar
      renderInfoPanel(nodeId);
    }}

    function deselectNode() {{
      selectedNode = null;
      highlightedNodes.clear();
      highlightedEdges.clear();
      renderer.refresh();
      
      document.getElementById("info-panel").classList.remove("open");
      tomSelectInstance.setValue("", true);
    }}

    // Bind WebGL canvas events
    renderer.on("clickNode", ({{ node }}) => {{
      focusNode(node);
      tomSelectInstance.setValue(node, true);
    }});

    renderer.on("clickStage", () => {{
      deselectNode();
    }});

    // Info sidebar detail rendering
    function renderInfoPanel(nodeId) {{
      const name = graph.getNodeAttribute(nodeId, "label");
      const category = graph.getNodeAttribute(nodeId, "category");
      const attributes = graph.getNodeAttribute(nodeId, "attributes") || {{}};
      const panel = document.getElementById("info-panel");
      const content = document.getElementById("info-content");

      let detailsHtml = `
        <span class="badge badge-${{category.toLowerCase()}}">${{category}}</span>
        <div class="entity-title">${{name}}</div>
      `;

      // Render custom attributes depending on node category
      if (category === "Formulation") {{
        if (attributes.dosage) {{
          detailsHtml += `
            <div class="props-group">
              <div class="prop-label">Recommended Dosage</div>
              <div class="prop-value">${{attributes.dosage}}</div>
            </div>
          `;
        }}
        if (attributes.preparation_method) {{
          detailsHtml += `
            <div class="props-group">
              <div class="prop-label">Preparation Method</div>
              <div class="prop-value">${{attributes.preparation_method}}</div>
            </div>
          `;
        }}
      }} else if (category === "Disease") {{
        if (attributes.symptoms) {{
          detailsHtml += `
            <div class="props-group">
              <div class="prop-label">Recorded Symptoms</div>
              <div class="prop-value">${{attributes.symptoms}}</div>
            </div>
          `;
        }}
        if (attributes.no_of_symptoms) {{
          detailsHtml += `
            <div class="props-group">
              <div class="prop-label">Number of Symptoms</div>
              <div class="prop-value">${{attributes.no_of_symptoms}}</div>
            </div>
          `;
        }}
      }}

      // Retrieve connected elements directly from Graphology
      const ingredients = [];
      const relationships = [];

      graph.forEachEdge(nodeId, (edge, edgeAttrs, source, target) => {{
        const otherNode = source === nodeId ? target : source;
        const otherName = graph.getNodeAttribute(otherNode, "label");
        const otherCat = graph.getNodeAttribute(otherNode, "category");
        const relType = edgeAttrs.label;
        
        relationships.push({{
          id: otherNode,
          name: otherName,
          category: otherCat,
          relation: relType
        }});
      }});

      // Group relationships
      if (relationships.length > 0) {{
        detailsHtml += `
          <div class="neighbors-section">
            <div class="neighbors-title">Connected Connections (${{relationships.length}})</div>
            <ul class="neighbors-list">
        `;
        
        relationships.sort((a,b) => a.name.localeCompare(b.name)).forEach(rel => {{
          detailsHtml += `
            <li onclick="focusNode('${{rel.id.replace(/'/g, "\\'")}}')">
              <span>${{rel.name}} <small style="color: var(--text-muted)">(${{rel.category}})</small></span>
              <span class="rel-badge">${{rel.relation}}</span>
            </li>
          `;
        }});

        detailsHtml += `
            </ul>
          </div>
        `;
      }}

      content.innerHTML = detailsHtml;
      panel.classList.add("open");
    }}

    // Zoom/Camera control APIs
    function zoomIn() {{
      camera.animatedZoom({{ factor: 1.5 }});
    }}

    function zoomOut() {{
      camera.animatedZoom({{ factor: 0.6 }});
    }}

    function resetCamera() {{
      camera.animate({{
        x: 0,
        y: 0,
        ratio: 1.0
      }}, {{ duration: 600 }});
    }}
  </script>
</body>
</html>
"""

    print("Writing HTML visualizer output...")
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_template)
        
    print(f"Success! WebGL Visualizer generated at: {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
