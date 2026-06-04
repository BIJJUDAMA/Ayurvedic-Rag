import json
import os
from .parser import parse_shusrut_samhita
from .config import FILE_PATH, SOURCE

def main(model=None):
    print("Starting Susruta Samhita worker...")
    chunks = parse_shusrut_samhita(FILE_PATH)
    
    output_dir = os.path.join("processed-books", SOURCE)
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Write Canonical Markdown
    md_path = os.path.join(output_dir, "canonical.md")
    with open(md_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(f"## {chunk['title']}\n\n{chunk['content']}\n\n")
    
    # 2. Write Vectors JSONL
    jsonl_path = os.path.join(output_dir, "vectors.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk) + "\n")
            
    print(f"Artifacts generated in {output_dir}")

if __name__ == "__main__":
    main()
