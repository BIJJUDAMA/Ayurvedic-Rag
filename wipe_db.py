import sys
from qdrant_client import QdrantClient

# The production collection name for the 2026 Unified Suite
COLLECTION_NAME = "ayurveda_rag"

def wipe_db():
    try:
        client = QdrantClient(host="localhost", port=6333)
        collections_res = client.get_collections()
        existing_collections = [c.name for c in collections_res.collections]
    except Exception as e:
        print(f"Error: Could not connect to Qdrant at localhost:6333.\n{e}")
        return

    print("\n" + "="*40)
    print("AYURVEDA RAG: DATABASE WIPE TOOL")
    print("="*40)
    print(f"Active Collections: {existing_collections}")
    print(f"Target Collection:  '{COLLECTION_NAME}'")
    print("-" * 40)
    
    if COLLECTION_NAME not in existing_collections:
        print(f"Notice: Collection '{COLLECTION_NAME}' does not exist.")
        choice = input("Do you want to wipe a DIFFERENT collection? (type name or 'no'): ").strip()
        if choice.lower() == 'no' or not choice:
            return
        target = choice
    else:
        target = COLLECTION_NAME

    confirm = input(f"Are you sure you want to PERMANENTLY DELETE '{target}'? (type 'yes' to proceed): ").strip().lower()
    
    if confirm == 'yes':
        try:
            print(f"Deleting '{target}'...")
            client.delete_collection(collection_name=target)
            print(f"✔ Successfully wiped: {target}")
        except Exception as e:
            print(f"✘ Error deleting collection: {e}")
    else:
        print("Operation cancelled.")

    print("\nDone.")

if __name__ == "__main__":
    wipe_db()
