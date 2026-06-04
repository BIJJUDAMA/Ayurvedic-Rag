import os
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from rich.console import Console
from rich.panel import Panel

# Global console for logging
_console = Console()

class Neo4jGraphTool:
    """
    Structured Knowledge Graph Tool for Ayurveda.
    Connects to Neo4j to perform clinical relationship lookups for 
    Diseases, Plants, and Formulations.
    """
    def __init__(self, 
                 uri: str = "bolt://localhost:7687", 
                 user: str = "neo4j", 
                 password: str = "1234", 
                 console: Optional[Console] = None):
        self.uri = uri
        self.user = user
        self.password = password
        self.console = console or _console
        self.driver = None
        
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            self.console.print("[info]Connected to Neo4j Knowledge Graph at bolt://localhost:7687[/]")
        except Exception as e:
            self.console.print(f"[bold red][!] Neo4j Connection Error:[/] {e}")
            self.console.print("[info][*] Tip: Ensure Neo4j is running in Docker and reachable at localhost:7687.[/]")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def query_knowledge_graph(self, entity_name: str) -> str:
        """
        CLINICAL VALIDATION & RELATIONSHIP TOOL:
        Retrieves hard clinical facts and validated relationships from the Ayurveda Knowledge Graph.
        
        STRICT USAGE RULE:
        - USE this tool when the query mentions a specific Disease (e.g., 'Arsha', 'Jwara'), 
          Plant (e.g., 'Haritaki', 'Pippali'), or Formulation (e.g., 'Abhayarista').
        - It returns validated Treatment relationships, Ingredients, and Dosages.
        - This provides the "Siddhanta" (proven fact) while semantic search provides "Pramana" (evidence).
        """
        if not self.driver:
            return "ERROR: Neo4j knowledge graph is not reachable. Ensure the container is running and 'neo4j' package is installed."

        self.console.print(f"[bold cyan]Neo4j Lookup:[/] Searching for clinical links for '{entity_name}'...")

        # Comprehensive Cypher Query to fetch node details and outgoing/incoming relationships
        cypher = """
        MATCH (n)
        WHERE n.name =~ ('(?i).*' + $name + '.*') OR n.id =~ ('(?i).*' + $name + '.*')
        WITH n LIMIT 1
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n, labels(n) as labels, 
               collect({
                   rel_type: type(r), 
                   target_name: m.name, 
                   target_labels: labels(m),
                   props: properties(r),
                   direction: CASE WHEN startNode(r) = n THEN 'OUT' ELSE 'IN' END
               }) as relationships
        """

        try:
            with self.driver.session() as session:
                result = session.run(cypher, name=entity_name)
                record = result.single()
                
                if not record:
                    return f"NOT_FOUND: No clinical entity matching '{entity_name}' found in the knowledge graph."

                node = record["n"]
                labels = record["labels"]
                rels = record.get("relationships", [])

                res_str = f"ENTITY: {node.get('name', 'Unknown')} ({', '.join(labels)})\n"
                
                # Format attributes (Node Properties)
                attrs = dict(node)
                if attrs:
                    res_str += "ATTRIBUTES (Canonical Data):\n"
                    for k, v in attrs.items():
                        if k not in ['name', 'id'] and v:
                            res_str += f"  - {k.replace('_', ' ').capitalize()}: {v}\n"

                # Format relationships
                if rels and any(r['target_name'] for r in rels):
                    res_str += "VALIDATED CLINICAL RELATIONSHIPS:\n"
                    # Sort relationships by type for better readability
                    sorted_rels = sorted(rels, key=lambda x: (x['rel_type'] or '', x['target_name'] or ''))
                    for r in sorted_rels:
                        if not r['target_name']: continue
                        
                        rel_info = f"  - {r['rel_type']}"
                        if r['direction'] == 'OUT':
                            rel_info += f" -> {r['target_name']}"
                        else:
                            rel_info += f" <- {r['target_name']}"
                        
                        rel_info += f" ({', '.join(r['target_labels'])})"
                        
                        # Add relationship properties (e.g., dosage, part used)
                        props = r.get('props', {})
                        if props:
                            prop_details = []
                            for pk, pv in props.items():
                                if pv and pk not in ['pharmacopoeia_ref', 'Source_db']:
                                    prop_details.append(f"{pk.replace('_', ' ')}: {pv}")
                            if prop_details:
                                rel_info += f" [Details: {', '.join(prop_details)}]"
                                
                        res_str += rel_info + "\n"
                
                self.console.print(Panel(res_str, title="[bold blue]KNOWLEDGE GRAPH EVIDENCE[/]", border_style="blue"))
                return res_str

        except Exception as e:
            return f"ERROR: Knowledge graph query failed: {str(e)}"
