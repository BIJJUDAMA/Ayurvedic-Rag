import os
import subprocess
from rich.console import Console

_console = Console()

def ingest_graph():
    """Runs the Neo4j ingestion script via cypher-shell in the Docker container."""
    _console.print("\n[bold blue]>>> Knowledge Graph Ingestion (Neo4j)...[/]")
    
    # Command to execute Cypher script inside the container
    # Note: /var/lib/neo4j/import is mapped to ./graph/data in docker-compose
    command = [
        "docker", "exec", "grayu-neo4j", 
        "cypher-shell", "-u", "neo4j", "-p", "1234", 
        "-f", "/var/lib/neo4j/import/import.cypher"
    ]
    
    try:
        # Check if container is running
        check_container = subprocess.run(
            ["docker", "ps", "--filter", "name=grayu-neo4j", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        
        if "grayu-neo4j" not in check_container.stdout:
            _console.print("[bold red][!] Error:[/] Neo4j container 'grayu-neo4j' is not running.")
            _console.print("[info][*] Tip: Run 'docker-compose up -d' first.[/]")
            return False

        _console.print("[info]Executing Cypher import script inside container...")
        # Using shell=True for windows compatibility if needed, but list is safer
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode == 0:
            _console.print("[bold green][OK] Knowledge Graph ingested successfully.[/]")
            # Log summary of nodes if possible
            return True
        else:
            _console.print(f"[bold red][!] Ingestion Failed:[/] {result.stderr}")
            if "APOC" in result.stderr:
                _console.print("[info][*] Tip: Ensure APOC plugin is enabled in Neo4j environment settings.[/]")
            return False
            
    except subprocess.CalledProcessError:
        _console.print("[bold red][!] Error:[/] Could not verify container status. Is Docker installed?")
        return False
    except Exception as e:
        _console.print(f"[bold red][!] Exception during graph ingestion:[/] {e}")
        return False

if __name__ == "__main__":
    ingest_graph()
