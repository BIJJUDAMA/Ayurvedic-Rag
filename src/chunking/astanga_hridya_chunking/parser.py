import re
import uuid
from typing import List, Dict, Any, Optional
from .utils import is_devanagari, extract_verse_numbers
from .noise_manifest import clean_noise

def clean_content(text: str) -> str:
    text = clean_noise(text)
    import html
    return html.unescape(text).strip()

def generate_stable_id(content_seed: str) -> str:
    """Generate a deterministic UUID from content."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, content_seed))

def create_verse_chunk(section_id, chapter_id, ch_num, ch_title, sec_title, buffer, verse_idx):
    content = clean_content("\n".join(buffer))
    if not content: return None
    
    verse_id = generate_stable_id(f"verse_{section_id}_{verse_idx}")
    return {
        "id": verse_id,
        "level": "verse",
        "parent_id": section_id,
        "title": f"{sec_title} - Block {verse_idx}",
        "content": content,
        "metadata": {
            "chapter_number": ch_num,
            "chapter_title": ch_title,
            "section_title": sec_title,
            "has_sanskrit": is_devanagari(content),
            "word_count": len(content.split())
        }
    }

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
        "title": "Astanga Hridaya",
        "content": "Astanga Hridaya - The heart of the eight branches of Ayurveda.",
        "metadata": {"title": "Astanga Hridaya"}
    })

    # 2. Sthana Node
    chunks.append({
        "id": sthana_id,
        "level": "sthana_index",
        "parent_id": treatise_root_id,
        "title": "Sutra Sthana",
        "content": "Sutra Sthana: Section on Fundamental Principles.",
        "metadata": {"title": "Sutra Sthana"}
    })

    current_chapter_id = None
    current_chapter_num = 0
    current_chapter_title = "Introductory Metadata"
    
    # Default to a generic root if before first chapter
    current_chapter_id = generate_stable_id("astanga_initial_root")
    chunks.append({
        "id": current_chapter_id,
        "level": "chapter",
        "parent_id": sthana_id,
        "title": "Introduction",
        "content": "Introductory sections of Astanga Hridaya.",
        "metadata": {"chapter_number": 0, "chapter_title": "Introduction"}
    })

    current_section_id = generate_stable_id("astanga_initial_section")
    current_section_title = "Preface"
    chunks.append({
        "id": current_section_id,
        "level": "section",
        "parent_id": current_chapter_id,
        "title": "Preface",
        "content": "Preface and introductory notes.",
        "metadata": {"section_title": "Preface"}
    })

    current_verse_buffer = []
    verse_count = 0

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    def flush_verse():
        nonlocal verse_count
        if current_verse_buffer and current_section_id:
            v_chunk = create_verse_chunk(
                current_section_id, current_chapter_id, 
                current_chapter_num, current_chapter_title, 
                current_section_title, current_verse_buffer, verse_count
            )
            if v_chunk:
                chunks.append(v_chunk)
                verse_count += 1
            current_verse_buffer.clear()
            return True
        return False

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line: continue
        
        # Rule 1: Chapter boundary
        chapter_match = re.match(r'^## Chapter (\d+)[ :]*(.*)', stripped_line)
        if chapter_match:
            flush_verse()
            
            current_chapter_num = int(chapter_match.group(1))
            current_chapter_title = chapter_match.group(2).strip()
            current_chapter_id = generate_stable_id(f"ch_{current_chapter_num}_{current_chapter_title}")
            
            chunks.append({
                "id": current_chapter_id,
                "level": "chapter",
                "parent_id": sthana_id,
                "title": f"Chapter {current_chapter_num}: {current_chapter_title}",
                "content": stripped_line,
                "metadata": {
                    "chapter_number": current_chapter_num,
                    "chapter_title": current_chapter_title
                }
            })
            
            # Reset section to Chapter Introduction
            current_section_title = "Chapter Introduction"
            current_section_id = generate_stable_id(f"ch_{current_chapter_num}_intro")
            verse_count = 0
            
            chunks.append({
                "id": current_section_id,
                "level": "section",
                "parent_id": current_chapter_id,
                "title": current_section_title,
                "content": f"Introduction and summary of Chapter {current_chapter_num}: {current_chapter_title}",
                "metadata": {
                    "chapter_number": current_chapter_num,
                    "chapter_title": current_chapter_title,
                    "section_title": current_section_title
                }
            })
            continue

        # Rule 5: Ignore Anomaly 1
        if stripped_line == "## Astanga Hridaya Sutrasthan":
            continue

        # Rule 3: Section boundary (English headings)
        if stripped_line.startswith("##"):
            title_candidate = stripped_line.replace("##", "").strip()
            
            # Rule 2: Shloka detection (Devanagari headings start a new VERSE, not a new SECTION)
            if is_devanagari(title_candidate):
                flush_verse()
                current_verse_buffer.append(stripped_line)
                continue
            
            # Roman heading -> New Section
            flush_verse()
            
            current_section_title = title_candidate
            current_section_id = generate_stable_id(f"ch_{current_chapter_num}_{current_section_title}")
            verse_count = 0
            
            verse_info = extract_verse_numbers(current_section_title)
            
            chunks.append({
                "id": current_section_id,
                "level": "section",
                "parent_id": current_chapter_id,
                "title": current_section_title,
                "content": f"Topic: {current_section_title} in Chapter {current_chapter_num}.",
                "metadata": {
                    "chapter_number": current_chapter_num,
                    "chapter_title": current_chapter_title,
                    "section_title": current_section_title,
                    "verse_start": verse_info["verse_start"],
                    "verse_end": verse_info["verse_end"]
                }
            })
            
            # VIRTUAL GLOSSARY: Promote header to a glossary stub
            glossary_id = generate_stable_id(f"glossary_astanga_{current_section_title}")
            chunks.append({
                "id": glossary_id,
                "level": "stub_glossary",
                "parent_id": current_section_id,
                "title": current_section_title,
                "content": f"Topic: {current_section_title}. Found in Astanga Hridaya, Chapter {current_chapter_num}.",
                "metadata": {
                    "title": current_section_title,
                    "source": "astanga_hridaya",
                    "context": "promoted_header"
                }
            })
            continue

        # Default: Append to buffer
        if current_section_id:
            current_verse_buffer.append(line)

    # Final flush
    flush_verse()

    # Link sequential edges (prev_id/next_id)
    # Verse to Verse
    for i in range(len(chunks)):
        if chunks[i]["level"] == "verse":
            for j in range(i + 1, len(chunks)):
                if chunks[j]["level"] == "verse" and chunks[j]["parent_id"] == chunks[i]["parent_id"]:
                    chunks[i]["next_id"] = chunks[j]["id"]
                    chunks[j]["prev_id"] = chunks[i]["id"]
                    break
    
    # Section to Section
    for i in range(len(chunks)):
        if chunks[i]["level"] == "section":
            for j in range(i + 1, len(chunks)):
                if chunks[j]["level"] == "section" and chunks[j]["parent_id"] == chunks[i]["parent_id"]:
                    chunks[i]["next_id"] = chunks[j]["id"]
                    chunks[j]["prev_id"] = chunks[i]["id"]
                    break

    return chunks
