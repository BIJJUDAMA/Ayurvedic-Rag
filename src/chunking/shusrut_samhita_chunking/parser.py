import re
import uuid
from typing import List, Dict, Any, Optional
from enum import Enum, auto
from .noise_manifest import clean_noise
from .utils import (
    is_indological_truths, is_citation_marker, is_base64_image,
    extract_verse_info, get_chapter_title_from_intro,
    split_long_section
)

class ParserState(Enum):
    FRONTMATTER = auto()
    CHAPTER_HEADER = auto()
    CHAPTER_PREAMBLE = auto() # Collecting Summary
    CHAPTER_BODY = auto()
    APPARATUS = auto()

def clean_text(text: str) -> str:
    text = clean_noise(text)
    import html
    return html.unescape(text).strip()

def generate_stable_id(content_seed: str) -> str:
    """Generate a deterministic UUID from content."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, content_seed))

def is_section_heading(line: str) -> bool:
    """Detects if a line is likely a section heading."""
    stripped = line.strip()
    if not stripped: return False
    if stripped.startswith("##"): 
        if is_indological_truths(stripped) or is_citation_marker(stripped):
            return False
        return True
    
    # Match verse numbers at start of line: "1.", "16, 17/1.", "20/2, 21/1."
    if re.match(r'^\d+([\s,/-]+\d+([/\.]\d+)?)?[\.\s]+[A-Z]', stripped):
        return True
        
    return False

def parse_shusrut_samhita(file_path: str) -> List[Dict[str, Any]]:
    chunks = []
    
    # Global Hierarchy
    treatise_root_id = generate_stable_id("root_susruta_samhita")
    sthana_id = generate_stable_id("sthana_nidana_susruta")
    
    state = ParserState.FRONTMATTER
    intro_buffer = []
    summary_buffer = []
    section_buffer = []
    
    current_chapter_num = 0
    current_chapter_id = None
    current_ss_ref = ""
    
    num_map = {
        "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6,
        "Seven": 7, "Eight": 8, "Nine": 9, "Ten": 10, "Eleven": 11,
        "Twelve": 12, "Thirteen": 13, "Fourteen": 14, "Fifteen": 15, "Sixteen": 16
    }

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    line_idx = 0
    while line_idx < len(lines):
        line = lines[line_idx]
        stripped = line.strip()
        
        # 1. Global Filters
        if is_indological_truths(line) or is_base64_image(line) or stripped in ["---", "--"]:
            line_idx += 1
            continue
            
        # 2. Record SS citation markers (Metadata source)
        if is_citation_marker(line):
            match = re.search(r'S\.S\.\s*II\.\s*(\d+)', stripped)
            if match:
                current_ss_ref = f"S.S.II.{match.group(1)}"
            line_idx += 1
            continue

        # 3. Chapter Transition Trigger
        if "CHAPTER" in stripped.upper() and ("NIDANA" in stripped.upper() or "NIDÃNA" in stripped.upper()):
            if "THUS ENDS" in stripped.upper():
                line_idx += 1
                continue

            if section_buffer:
                flush_sections(chunks, section_buffer, current_chapter_id, current_chapter_num, get_chapter_title_from_intro(current_chapter_num))
                section_buffer = []
            
            match = re.search(r'CHAPTER\s+([A-Z]+|\d+)', stripped, re.I)
            if match:
                raw_num = match.group(1).title()
                if raw_num in num_map:
                    current_chapter_num = num_map[raw_num]
                elif raw_num.upper() in [k.upper() for k in num_map.keys()]:
                    for k, v in num_map.items():
                        if k.upper() == raw_num.upper():
                            current_chapter_num = v
                            break
                elif raw_num.isdigit():
                    current_chapter_num = int(raw_num)
            
            state = ParserState.CHAPTER_HEADER
            summary_buffer = []
            chapter_title = get_chapter_title_from_intro(current_chapter_num)
            current_chapter_id = generate_stable_id(f"ss_ch_{current_chapter_num}_{chapter_title}")
            
            line_idx += 1
            continue

        # 4. State Management
        if state == ParserState.FRONTMATTER:
            if "INTRODUCTION" in stripped.upper():
                state = ParserState.FRONTMATTER
            intro_buffer.append(line)
            
        if stripped == "## SUMMARY":
            state = ParserState.CHAPTER_PREAMBLE
            line_idx += 1
            continue
            
        if state in [ParserState.CHAPTER_HEADER, ParserState.CHAPTER_PREAMBLE]:
            if stripped.startswith("## Chapter") or is_section_heading(line):
                # Add Chapter Chunk
                chapter_title = get_chapter_title_from_intro(current_chapter_num)
                if not any(c["id"] == current_chapter_id for c in chunks):
                    chunks.append({
                        "id": current_chapter_id,
                        "level": "chapter",
                        "parent_id": sthana_id,
                        "title": f"Chapter {current_chapter_num}: {chapter_title}",
                        "content": f"Full diagnosis and etiology in Chapter {current_chapter_num}.",
                        "metadata": {
                            "chapter_number": current_chapter_num,
                            "chapter_title": chapter_title,
                            "ss_reference": current_ss_ref
                        }
                    })
                
                # If we had a summary, flush it as a special child
                if summary_buffer:
                    summary_text = clean_text("\n".join(summary_buffer))
                    chunks.append({
                        "id": generate_stable_id(f"ss_ch_{current_chapter_num}_summary"),
                        "level": "section",
                        "parent_id": current_chapter_id,
                        "title": "Chapter Summary",
                        "content": summary_text,
                        "metadata": {"chapter_number": current_chapter_num, "is_summary": True}
                    })
                    summary_buffer = []

                state = ParserState.CHAPTER_BODY
            elif state == ParserState.CHAPTER_PREAMBLE:
                summary_buffer.append(line)
                line_idx += 1
                continue

        if state == ParserState.CHAPTER_BODY:
            if "SUGGESTED RESEARCH PROBLEMS" in stripped.upper():
                if section_buffer:
                    flush_sections(chunks, section_buffer, current_chapter_id, current_chapter_num, get_chapter_title_from_intro(current_chapter_num))
                    section_buffer = []
                state = ParserState.APPARATUS
            elif is_section_heading(line):
                if section_buffer:
                    flush_sections(chunks, section_buffer, current_chapter_id, current_chapter_num, get_chapter_title_from_intro(current_chapter_num))
                section_buffer = [line]
            else:
                section_buffer.append(line)

        line_idx += 1

    # Final flush
    if section_buffer and state == ParserState.CHAPTER_BODY:
        flush_sections(chunks, section_buffer, current_chapter_id, current_chapter_num, get_chapter_title_from_intro(current_chapter_num))

    # Add Root Nodes
    chunks.insert(0, {
        "id": treatise_root_id,
        "level": "book",
        "parent_id": None,
        "title": "Susruta Samhita",
        "content": "Susruta Samhita - Foundation text of Ancient Indian Surgery.",
        "metadata": {"title": "Susruta Samhita"}
    })

    chunks.insert(1, {
        "id": sthana_id,
        "level": "sthana_index",
        "parent_id": treatise_root_id,
        "title": "Nidana Sthana",
        "content": "Nidana Sthana: Etiology and Pathogenesis.",
        "metadata": {"title": "Nidana Sthana"}
    })

    return chunks

def flush_sections(chunks, buffer, chapter_id, chapter_num, chapter_title):
    if not buffer: return
    
    heading = buffer[0]
    verse_start, verse_end, title = extract_verse_info(heading)
    content = clean_text("\n".join(buffer))
    
    if not title:
        title = heading.strip()[:100]

    # Node ID based on chapter and title
    node_id = generate_stable_id(f"ss_{chapter_num}_{title}_{hash(content)}")
    
    chunks.append({
        "id": node_id,
        "level": "section",
        "parent_id": chapter_id,
        "title": title,
        "content": content,
        "metadata": {
            "chapter_number": chapter_num,
            "chapter_title": chapter_title,
            "section_title": title,
            "verse_start": verse_start,
            "verse_end": verse_end
        }
    })

    # VIRTUAL GLOSSARY: Promote to a glossary stub
    if len(title) > 3 and not title.isdigit():
        glossary_id = generate_stable_id(f"glossary_ss_{chapter_num}_{title}")
        chunks.append({
            "id": glossary_id,
            "level": "stub_glossary",
            "parent_id": node_id,
            "title": title,
            "content": f"Term: {title}. Susruta Samhita, Chapter {chapter_num}.",
            "metadata": {"source": "shusrut_samhita"}
        })
