import os
import json
from .config import BOOKS_DIR, TYPE_STHANA, SOURCE_TREATISE
from .utils import SlugRegistry
from .parser import CharakaParser
from src.chunking.unified_database import upload_to_qdrant

def main(model=None):
    registry = SlugRegistry()
    parser = CharakaParser(registry)
    all_chunks = []

    # Pass 0: Create High-Level Hierarchy (Book & Sthanas)
    print("Creating High-Level Hierarchy...")
    
    # 1. Treatise Root
    treatise_root = {
        "id": parser.treatise_root_id,
        "level": "book",
        "parent_id": None,
        "title": "Charaka Samhita",
        "content": "Charaka Samhita - The foundational text of Ayurveda.",
        "url": "https://charakasamhita.com/",
        "metadata": {"author": "Charaka / Agnivesha / Dridhabala"}
    }
    all_chunks.append(treatise_root)

    # 2. Sthana Nodes
    sthanas = [
        ("Sutra Sthana", "Section on Fundamental Principles", "Sutra_Sthana"),
        ("Nidana Sthana", "Section on Diagnosis", "Nidana_Sthana"),
        ("Vimana Sthana", "Section on Specific Determination", "Vimana_Sthana"),
        ("Sharira Sthana", "Section on Anatomy/Physiology", "Sharira_Sthana"),
        ("Indriya Sthana", "Section on Prognosis", "Indriya_Sthana"),
        ("Chikitsa Sthana", "Section on Therapeutics", "Chikitsa_Sthana"),
        ("Kalpa Sthana", "Section on Pharmaceutics", "Kalpa_Sthana"),
        ("Siddhi Sthana", "Section on Successful Treatment", "Siddhi_Sthana")
    ]
    
    for name, desc, key in sthanas:
        sid = parser.hierarchy.sthana_ids[key]
        all_chunks.append({
            "id": sid,
            "level": TYPE_STHANA,
            "parent_id": parser.treatise_root_id,
            "title": name,
            "content": f"{name}: {desc}",
            "url": "https://charakasamhita.com/",
            "metadata": {"section_name": name}
        })

    # 3. New Hub Nodes for Materia Medica and Appendices
    all_chunks.append({
        "id": parser.hierarchy.meta_hub_id,
        "level": TYPE_STHANA,
        "parent_id": parser.treatise_root_id,
        "title": "Appendices & Meta",
        "content": "Administrative and Meta information regarding the Charaka Samhita Project.",
        "url": "https://charakasamhita.com/",
        "metadata": {}
    })
    
    all_chunks.append({
        "id": parser.hierarchy.materia_medica_id,
        "level": TYPE_STHANA,
        "parent_id": parser.treatise_root_id,
        "title": "Materia Medica",
        "content": "Glossary of herbs and botanical identifiers in Charaka Samhita.",
        "url": "https://charakasamhita.com/",
        "metadata": {}
    })

    # Pass 1: Discovery (Build Registry)
    print("Starting Discovery Pass...")
    files = [f for f in os.listdir(BOOKS_DIR) if f.endswith(".json")]
    for filename in files:
        file_path = os.path.join(BOOKS_DIR, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            registry.register(data["title"], data["url"])
    print(f"Discovery complete. Registered {len(registry.title_to_id)} unique titles.")

    # Pass 2: Indexing (Parse and Chunk)
    print("Starting Indexing Pass...")
    for filename in files:
        file_path = os.path.join(BOOKS_DIR, filename)
        print(f"Parsing {filename}...")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            chunks = parser.parse(data)
            all_chunks.extend(chunks)

    print(f"Parsing complete. Generated {len(all_chunks)} chunks.")

    # Pass 3: Upload to Qdrant
    if all_chunks:
        upload_to_qdrant(all_chunks, SOURCE_TREATISE, model=model)
    else:
        print("No chunks generated. Skipping upload.")

if __name__ == "__main__":
    main()
