import os
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Constants
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "ayurveda_rag"
VECTOR_SIZE = 1024 # Multilingual-E5-Large dimension

def init_collection():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    print(f"Checking for existing collection '{COLLECTION_NAME}'...")
    if client.collection_exists(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' already exists.")
        # In YOLO mode, we might want to be careful, but I'll assume we want to recreate for this upgrade
        confirm = input("Do you want to DELETE and RECREATE it for the Multi-Vector upgrade? (yes/no): ").strip().lower()
        if confirm == 'yes':
            client.delete_collection(COLLECTION_NAME)
            print("Deleted existing collection.")
        else:
            print("Initialization aborted.")
            return

    print(f"Creating collection '{COLLECTION_NAME}' with Industry-Standard Multi-Vector support...")
    
    # 1. Configuration for Dense Named Vectors
    # - dense_english: For semantic queries in English
    # - dense_sanskrit: For queries containing Sanskrit (IAST/Devanagari)
    vectors_config = {
        "dense_english": models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE
        ),
        "dense_sanskrit": models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE
        )
    }

    # 2. Configuration for Sparse SPLADE Vector
    sparse_vectors_config = {
        "sparse_splade": models.SparseVectorParams(
            index=models.SparseIndexParams(
                on_disk=False,
            )
        )
    }

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=vectors_config,
        sparse_vectors_config=sparse_vectors_config,
    )
    
    # 3. Create Payload Indexes for fast filtering
    print("Creating payload indexes...")
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="metadata.source",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="metadata.chapter_number",
        field_schema=models.PayloadSchemaType.INTEGER,
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="level",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    
    print(f"✔ Collection '{COLLECTION_NAME}' initialized successfully with SPLADE and Dense support.")

if __name__ == "__main__":
    init_collection()
