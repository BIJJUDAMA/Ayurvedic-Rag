from .parser import parse_astanga_hridaya
from src.chunking.unified_database import upload_to_qdrant
from .config import FILE_PATH, SOURCE_TREATISE

def main(model=None):
    print("Starting Astanga Hridaya parsing process...")
    processed_chunks = parse_astanga_hridaya(FILE_PATH)
    print(f"Parsing complete. Found {len(processed_chunks)} chunks.")
    upload_to_qdrant(processed_chunks, SOURCE_TREATISE, model=model)

if __name__ == "__main__":
    main()
