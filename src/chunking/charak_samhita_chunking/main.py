import json
import os
import sys
from .parser import CharakaParser
from .utils import SlugRegistry

def main(model=None):
    print("Starting Charaka Samhita worker (Stitching fragments)...")
    
    dir_path = os.path.join("books", "charak_samhita")
    registry = SlugRegistry()
    parser = CharakaParser(registry, dir_path=dir_path)
    
    all_chunks = []
    files = [f for f in os.listdir(dir_path) if f.endswith(".json")]
    
    # First pass: Register all slugs (Pre-scan)
    print(f"Registering {len(files)} files...")
    for filename in files:
        with open(os.path.join(dir_path, filename), "r", encoding="utf-8") as f:
            data = json.load(f)
            registry.register(data["title"], data["url"])
            
    # Second pass: Parse and collect chunks
    print("Parsing files...")
    
    # 0. Add Treatise Root Node
    all_chunks.append({
        "id": parser.treatise_root_id,
        "level": "book",
        "parent_id": None,
        "title": "Charaka Samhita",
        "content": "Charaka Samhita - Fundamental text on Internal Medicine (Kayachikitsa).",
        "metadata": {"title": "Charaka Samhita"}
    })

    for filename in files:
        with open(os.path.join(dir_path, filename), "r", encoding="utf-8") as f:
            data = json.load(f)
            chunks = parser.parse(data)
            all_chunks.extend(chunks)
            
    # Note: Complex sequential sorting by hierarchy could be done here, 
    # but for now we follow the file iteration order.
    
    output_dir = os.path.join("processed-books", "charak_samhita")
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Write Canonical Markdown
    md_path = os.path.join(output_dir, "canonical.md")
    with open(md_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            title = chunk.get('title') or "Untitled"
            f.write(f"## {title}\n\n{chunk['content']}\n\n")
            
    # 2. Write Vectors JSONL
    jsonl_path = os.path.join(output_dir, "vectors.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk) + "\n")
            
    print(f"Artifacts generated in {output_dir}. Total chunks: {len(all_chunks)}")

if __name__ == "__main__":
    main()
