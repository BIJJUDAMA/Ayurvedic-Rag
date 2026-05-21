from .parser import parse_shusrut_samhita
from src.chunking.unified_database import upload_to_qdrant
from .config import FILE_PATH, SOURCE_TREATISE

def main(model=None):
    print("Starting Susruta Samhita parsing process...")
    processed_chunks = parse_shusrut_samhita(FILE_PATH)
    print(f"Parsing complete. Found {len(processed_chunks)} chunks.")
    upload_to_qdrant(processed_chunks, SOURCE_TREATISE, model=model)

if __name__ == "__main__":
    main()
