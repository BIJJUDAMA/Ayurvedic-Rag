import sys
import os

# 1. Add project root to sys.path immediately
# This MUST happen before any local imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
import numpy as np
from src.chunking.remote_embedder import RemoteEmbedder

def check_environment():
    """Verify basic connectivity."""
    print("Checking environment...")
    sys.stdout.flush()

    # Check Qdrant
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host="localhost", port=6333)
        client.get_collections()
        print(" [OK] Qdrant is reachable.")
    except Exception as e:
        print(f" [!] Error: Qdrant is not reachable: {e}")
        return False

    # Check GPU Sidecar
    remote = RemoteEmbedder()
    if remote.is_available():
        print(" [OK] GPU Sidecar is reachable.")
    else:
        print(" [!] Error: GPU Sidecar is not reachable at http://localhost:8080")
        print("     Please run 'docker-compose up -d' first.")
        return False

    return True

def run_all(shared_model=None):
    """Execute all three pipelines sequentially with a shared model instance."""
    print("\n>>> Starting Full Pipeline (Unified) ...")
    
    if shared_model is None:
        shared_model = RemoteEmbedder()
        if not shared_model.is_available():
            print(" [!] Cannot proceed without GPU Sidecar.")
            return
    
    # Import and run pipelines one by one
    print("\n--- Phase 1: Susruta Samhita ---")
    from src.chunking.shusrut_samhita_chunking.main import main as run_susruta
    run_susruta(model=shared_model)
    
    print("\n--- Phase 2: Astanga Hridaya ---")
    from src.chunking.astanga_hridya_chunking.main import main as run_astanga
    run_astanga(model=shared_model)
    
    print("\n--- Phase 3: Charaka Samhita ---")
    from src.chunking.charak_samhita_chunking.main import main as run_charaka
    run_charaka(model=shared_model)
    
    print("\n>>> All tasks completed successfully.")
    sys.stdout.flush()

def menu():
    print(f"\n--- Ayurveda Unified Suite (Root: {project_root}) ---")
    shared_model = None

    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            if check_environment():
                run_all()
                return
        elif sys.argv[1] == "--charaka":
            if check_environment():
                from src.chunking.charak_samhita_chunking.main import main as run_charaka
                run_charaka()
                return

    if not check_environment():
        print(" [!] Environment check failed. Exiting.")
        return

    while True:
        print("\n=== Ayurveda Unified Chunking Suite ===")
        print("1. Run Charaka Samhita Pipeline")
        print("2. Run Susruta Samhita Pipeline")
        print("3. Run Astanga Hridaya Pipeline")
        print("4. Run ALL (Sequential)")
        print("5. Exit")
        sys.stdout.flush()
        
        try:
            choice = input("\nSelect an option (1-5): ").strip()
        except EOFError:
            print("\nNon-interactive mode detected. Use '--all' flag for background runs.")
            break

        if choice in ["1", "2", "3"]:
            if shared_model is None:
                shared_model = RemoteEmbedder()
            
            if choice == "1":
                from src.chunking.charak_samhita_chunking.main import main as run_charaka
                run_charaka(model=shared_model)
            elif choice == "2":
                from src.chunking.shusrut_samhita_chunking.main import main as run_susruta
                run_susruta(model=shared_model)
            elif choice == "3":
                from src.chunking.astanga_hridya_chunking.main import main as run_astanga
                run_astanga(model=shared_model)
        elif choice == "4":
            run_all(shared_model=shared_model)
        elif choice == "5":
            print("Exiting.")
            break
        else:
            print("Invalid option.")
        sys.stdout.flush()

if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"\n [!] Unhandled Exception: {e}")
        import traceback
        traceback.print_exc()
    sys.stdout.flush()
