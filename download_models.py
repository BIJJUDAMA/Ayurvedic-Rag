import os
from huggingface_hub import snapshot_download
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")

def download_model(model_name: str, save_dir: str):
    print(f"\n--- Downloading '{model_name}' to '{save_dir}' ---")
    
    # Use the token if provided in .env
    token = HF_TOKEN if HF_TOKEN and HF_TOKEN != "your_huggingface_token_here" else None
    
    if not token and "naver" in model_name:
        print(f"⚠ Warning: '{model_name}' is a gated repository. Download may fail without a valid HF_TOKEN in .env.")

    snapshot_download(
        repo_id=model_name,
        local_dir=save_dir,
        token=token,
        ignore_patterns=["*.msgpack", "*.h5", "onnx/*"]
    )
    
    print(f"✔ Model successfully saved to '{save_dir}'")

if __name__ == "__main__":
    # Ensure models directory exists
    os.makedirs("models", exist_ok=True)

    # 1. Primary Embedding Model: Multilingual-E5-Large (1024 Dims)
    # The 'Brain' for cross-lingual English-Sanskrit mapping.
    EMBED_NAME = "intfloat/multilingual-e5-large"
    EMBED_SAVE_PATH = os.path.join("models", "multilingual-e5-large")
    download_model(EMBED_NAME, EMBED_SAVE_PATH)

    # 2. Sparse Keyword Expansion: SPLADE v3
    # The 'Precision' layer for technical Ayurvedic terminology.
    SPLADE_NAME = "naver/splade-v3"
    SPLADE_SAVE_PATH = os.path.join("models", "splade-v3")
    download_model(SPLADE_NAME, SPLADE_SAVE_PATH)

    # 3. Reranker Model: BGE-Reranker-Base
    # The 'Judge' that scores top candidates with high precision.
    RERANK_NAME = "BAAI/bge-reranker-base"
    RERANK_SAVE_PATH = os.path.join("models", "bge-reranker-base")
    download_model(RERANK_NAME, RERANK_SAVE_PATH)

    print("\n" + "="*50)
    print("ALL MODELS DOWNLOADED SUCCESSFULLY.")
    print("You can now start the GPU Sidecar with 'docker-compose up -d'.")
    print("="*50)
