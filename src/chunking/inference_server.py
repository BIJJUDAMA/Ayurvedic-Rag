import os
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from sentence_transformers import SentenceTransformer, CrossEncoder
from transformers import AutoModelForMaskedLM, AutoTokenizer
import uvicorn
import numpy as np

app = FastAPI(title="Ayurveda Inference Service (GPU)")

# Configuration
EMBED_MODEL_PATH = "/models/multilingual-e5-large"
RERANK_MODEL_PATH = "/models/bge-reranker-base"
SPLADE_MODEL_ID = "/models/splade-v3"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Loading Multilingual-E5-Large from {EMBED_MODEL_PATH} on {DEVICE}...")
embed_model = SentenceTransformer(EMBED_MODEL_PATH, device=DEVICE)

print(f"Loading reranker model from {RERANK_MODEL_PATH} on {DEVICE}...")
rerank_model = CrossEncoder(RERANK_MODEL_PATH, device=DEVICE)

print(f"Loading SPLADE model from {SPLADE_MODEL_ID} on {DEVICE}...")
splade_tokenizer = AutoTokenizer.from_pretrained(SPLADE_MODEL_ID)
splade_model = AutoModelForMaskedLM.from_pretrained(SPLADE_MODEL_ID).to(DEVICE)

print("All models loaded successfully.")

class EmbedRequest(BaseModel):
    sentences: List[str]

class EmbedResponse(BaseModel):
    embeddings: List[List[float]]

class SparseEmbedResponse(BaseModel):
    # Dictionary of token_id: weight
    sparse_embeddings: List[Dict[int, float]]

class RerankRequest(BaseModel):
    query: str
    documents: List[str]

class RerankResponse(BaseModel):
    scores: List[float]

@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    try:
        embeddings = embed_model.encode(request.sentences)
        return EmbedResponse(embeddings=embeddings.tolist())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sparse-embed", response_model=SparseEmbedResponse)
async def sparse_embed(request: EmbedRequest):
    try:
        # Simple SPLADE implementation
        inputs = splade_tokenizer(request.sentences, return_tensors="pt", padding=True, truncation=True).to(DEVICE)
        with torch.no_grad():
            logits = splade_model(**inputs).logits
            
        # Log-saturation effect
        vec = torch.max(torch.log(1 + torch.relu(logits)) * inputs.attention_mask.unsqueeze(-1), dim=1)[0]
        
        results = []
        for i in range(vec.shape[0]):
            # Get non-zero indices and values
            cols = vec[i].nonzero().squeeze().cpu().numpy()
            if cols.ndim == 0: cols = np.array([cols])
            weights = vec[i][cols].cpu().numpy()
            results.append({int(c): float(w) for c, w in zip(cols, weights)})
            
        return SparseEmbedResponse(sparse_embeddings=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    try:
        pairs = [[request.query, doc] for doc in request.documents]
        scores = rerank_model.predict(pairs)
        return RerankResponse(scores=scores.tolist())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "device": DEVICE}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
