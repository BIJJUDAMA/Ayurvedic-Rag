import re
import uuid
from typing import List, Dict, Any
from .utils import is_devanagari, clean_content, extract_verse_numbers

def create_section_chunk(section_id, chapter_id, prev_id, ch_num, ch_title, sec_title, buffer):
    content = clean_content(buffer)
    verse_info = extract_verse_numbers(sec_title)
    return {
        "id": section_id,
        "level": "section",
        "parent_id": chapter_id,
        "prev_id": prev_id,
        "next_id": None,
        "content": content,
        "metadata": {
            "chapter_number": ch_num,
            "chapter_title": ch_title,
            "section_title": sec_title,
            "verse_start": verse_info["verse_start"],
            "verse_end": verse_info["verse_end"],
            "has_sanskrit": is_devanagari(content),
            "word_count": len(content.split())
        }
    }

def generate_stable_id(content_seed: str) -> str:
    """Generate a deterministic UUID from content."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, content_seed))

def parse_astanga_hridaya(file_path: str) -> List[Dict[str, Any]]:
    chunks = []
    # Global Hierarchy
    treatise_root_id = generate_stable_id("root_astanga_hridaya")
    sthana_id = generate_stable_id("sthana_sutra_astanga")
    
    # 1. Treatise Root
    chunks.append({
        "id": treatise_root_id,
        "level": "book",
        "parent_id": None,
        "content": "Astanga Hridaya - The heart of the eight branches of Ayurveda.",
        "metadata": {"title": "Astanga Hridaya"}
    })

    # 2. Sthana Node
    chunks.append({
        "id": sthana_id,
        "level": "sthana_index",
        "parent_id": treatise_root_id,
        "content": "Sutra Sthana: Section on Fundamental Principles.",
        "metadata": {"title": "Sutra Sthana"}
    })

    current_chapter_id = None
    current_chapter_num = 0
    current_chapter_title = ""
    
    current_section_id = None
    current_section_buffer = []
    current_section_title = ""
    prev_section_id = None

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        stripped_line = line.strip()
        
        # Rule 1: Chapter boundary
        chapter_match = re.match(r'^## Chapter (\d+)[ :]*(.*)', stripped_line)
        if chapter_match:
            # Flush current section before moving to new chapter
            if current_section_buffer:
                chunks.append(create_section_chunk(
                    current_section_id, current_chapter_id, prev_section_id,
                    current_chapter_num, current_chapter_title, current_section_title,
                    current_section_buffer
                ))
                prev_section_id = current_section_id
                current_section_buffer = []

            current_chapter_num = int(chapter_match.group(1))
            current_chapter_title = chapter_match.group(2).strip()
            current_chapter_id = generate_stable_id(f"ch_{current_chapter_num}_{current_chapter_title}")
            prev_section_id = None
            
            chunks.append({
                "id": current_chapter_id,
                "level": "chapter",
                "parent_id": sthana_id,
                "content": stripped_line,
                "metadata": {
                    "chapter_number": current_chapter_num,
                    "chapter_title": current_chapter_title
                }
            })
            
            # Start a "Chapter Intro" section immediately
            current_section_id = generate_stable_id(f"ch_{current_chapter_num}_intro")
            current_section_title = "Chapter Introduction"
            continue

        # Rule 5: Ignore Anomaly 1
        if stripped_line == "## Astanga Hridaya Sutrasthan":
            continue

        # Rule 3: Section boundary (English headings)
        section_match = re.match(r'^## (.*)', stripped_line)
        if section_match:
            title_candidate = section_match.group(1).strip()
            
            # Rule 2: Shloka detection (Devanagari headings are NOT boundaries)
            if is_devanagari(title_candidate):
                current_section_buffer.append(line)
                continue
            
            # Roman heading -> New Section
            if current_section_buffer:
                chunks.append(create_section_chunk(
                    current_section_id, current_chapter_id, prev_section_id,
                    current_chapter_num, current_chapter_title, current_section_title,
                    current_section_buffer
                ))
                prev_section_id = current_section_id

            current_section_id = generate_stable_id(f"ch_{current_chapter_num}_{title_candidate}")
            current_section_title = title_candidate
            current_section_buffer = [line]
            
            # VIRTUAL GLOSSARY: Promote header to a glossary stub to remove bias
            glossary_id = generate_stable_id(f"glossary_astanga_{title_candidate}")
            chunks.append({
                "id": glossary_id,
                "level": "stub_glossary",
                "parent_id": current_section_id, # Link back to the full section
                "content": f"Topic: {title_candidate}. Found in Astanga Hridaya, Chapter {current_chapter_num}.",
                "metadata": {
                    "title": title_candidate,
                    "source": "astanga_hridaya",
                    "context": "promoted_header"
                }
            })
            continue

        # Default: Append to buffer
        if current_section_id:
            current_section_buffer.append(line)

    # Final flush
    if current_section_buffer:
        chunks.append(create_section_chunk(
            current_section_id, current_chapter_id, prev_section_id,
            current_chapter_num, current_chapter_title, current_section_title,
            current_section_buffer
        ))

    # Link sequential edges
    for i in range(len(chunks)):
        if chunks[i]["level"] == "section":
            # Find next section
            for j in range(i + 1, len(chunks)):
                if chunks[j]["level"] == "section" and chunks[j]["metadata"]["chapter_number"] == chunks[i]["metadata"]["chapter_number"]:
                    chunks[i]["next_id"] = chunks[j]["id"]
                    chunks[j]["prev_id"] = chunks[i]["id"]
                    break
    
    return chunks
