import re
import uuid
from typing import List, Dict, Any, Optional
from enum import Enum, auto
from .utils import (
    is_indological_truths, is_citation_marker, is_base64_image,
    clean_text, extract_verse_info, get_chapter_title_from_intro,
    split_long_section
)

class ParserState(Enum):
    FRONTMATTER = auto()
    CHAPTER_HEADER = auto()
    CHAPTER_PREAMBLE = auto() # Collecting Summary
    CHAPTER_BODY = auto()
    APPARATUS = auto()

def generate_stable_id(content_seed: str) -> str:
    """Generate a deterministic UUID from content."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, content_seed))

def is_section_heading(line: str) -> bool:
    """
    Detects if a line is likely a section heading.
    Headings in this file either start with ## or with a verse number/range.
    """
    stripped = line.strip()
    if not stripped: return False
    if stripped.startswith("##"): 
        # Exclude metadata-only markers
        if is_indological_truths(stripped) or is_citation_marker(stripped):
            return False
        return True
    
    # Match verse numbers at start of line: "1.", "16, 17/1.", "20/2, 21/1.", "22/2, 23/1."
    # We look for digits followed by optional punctuation/ranges and then a space + capital letter
    if re.match(r'^\d+([\s,/-]+\d+([/\.]\d+)?)?[\.\s]+[A-Z]', stripped):
        return True
        
    return False

def parse_shusrut_samhita(file_path: str) -> List[Dict[str, Any]]:
    chunks = []
    
    # Global Hierarchy
    treatise_root_id = generate_stable_id("root_susruta_samhita")
    sthana_id = generate_stable_id("sthana_nidana_susruta")
    
    state = ParserState.FRONTMATTER
    
    # State-based buffers
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
        # Matches "CHAPTER ONE NIDÃNA-STHANA" or "CHAPTER TWO NIDANA STHANA"
        if "CHAPTER" in stripped.upper() and ("NIDANA" in stripped.upper() or "NIDÃNA" in stripped.upper()):
            if "THUS ENDS" in stripped.upper():
                line_idx += 1
                continue

            # Flush previous chapter
            if section_buffer:
                flush_sections(chunks, section_buffer, current_chapter_id, current_chapter_num, get_chapter_title_from_intro(current_chapter_num))
                section_buffer = []
            
            # Identify chapter number
            # Look for word numbers or digits
            match = re.search(r'CHAPTER\s+([A-Z]+|\d+)', stripped, re.I)
            if match:
                raw_num = match.group(1).title()
                # Try to map words, otherwise try int
                if raw_num in num_map:
                    current_chapter_num = num_map[raw_num]
                elif raw_num.upper() in [k.upper() for k in num_map.keys()]:
                    # Case insensitive map lookup
                    for k, v in num_map.items():
                        if k.upper() == raw_num.upper():
                            current_chapter_num = v
                            break
                elif raw_num.isdigit():
                    current_chapter_num = int(raw_num)
                else:
                    # Fallback or keep previous? Better to keep previous if we can't identify
                    pass
            
            # Set state and reset buffers
            state = ParserState.CHAPTER_HEADER
            summary_buffer = []
            chapter_title = get_chapter_title_from_intro(current_chapter_num)
            current_chapter_id = generate_stable_id(f"ss_ch_{current_chapter_num}_{chapter_title}")
            
            line_idx += 1
            continue

        # 4. State Management
        
        # State: FRONTMATTER
        if state == ParserState.FRONTMATTER:
            if "INTRODUCTION" in stripped.upper():
                state = ParserState.FRONTMATTER # Stay in frontmatter but start collecting
            intro_buffer.append(line)
            
        # State: Transition from Header/Preamble to Body
        if stripped == "## SUMMARY":
            state = ParserState.CHAPTER_PREAMBLE
            line_idx += 1
            continue
            
        # If we see a section heading or "## Chapter X", we move to BODY
        if state in [ParserState.CHAPTER_HEADER, ParserState.CHAPTER_PREAMBLE]:
            if stripped.startswith("## Chapter") or is_section_heading(line):
                # Flush summary if we were in PREAMBLE
                summary_text = clean_text("\n".join(summary_buffer))
                chapter_title = get_chapter_title_from_intro(current_chapter_num)
                
                # Check if chapter chunk already exists (avoid duplicates)
                if not any(c["id"] == current_chapter_id for c in chunks):
                    chunks.append({
                        "id": current_chapter_id,
                        "level": "chapter",
                        "parent_id": sthana_id,
                        "content": summary_text or f"Chapter {current_chapter_num}: {chapter_title}",
                        "metadata": {
                            "chapter_number": current_chapter_num,
                            "chapter_title": chapter_title,
                            "ss_reference": current_ss_ref
                        }
                    })
                
                state = ParserState.CHAPTER_BODY
                # Fall through to CHAPTER_BODY collection
            elif state == ParserState.CHAPTER_PREAMBLE:
                summary_buffer.append(line)
                line_idx += 1
                continue

        # State: CHAPTER_BODY
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

        # State: APPARATUS
        elif state == ParserState.APPARATUS:
            # Just ignore or collect if needed. For now, we skip.
            pass

        line_idx += 1

    # Final flush
    if section_buffer and state == ParserState.CHAPTER_BODY:
        flush_sections(chunks, section_buffer, current_chapter_id, current_chapter_num, get_chapter_title_from_intro(current_chapter_num))

    # Add Book Root and Sthana Node at the beginning
    # 1. Treatise Root
    chunks.insert(0, {
        "id": treatise_root_id,
        "level": "book",
        "parent_id": None,
        "content": "Susruta Samhita - One of the foundational surgical texts of Ayurveda.",
        "metadata": {"title": "Susruta Samhita"}
    })

    # 2. Sthana Node
    chunks.insert(1, {
        "id": sthana_id,
        "level": "sthana_index",
        "parent_id": treatise_root_id,
        "content": "Nidana Sthana: Section on Etiology and Pathogenesis.",
        "metadata": {"title": "Nidana Sthana"}
    })

    # 3. Intro / Preamble (Links to Sthana)
    book_content = clean_text("\n".join(intro_buffer))
    if book_content:
        chunks.append({
            "id": generate_stable_id("ss_nidana_intro"),
            "level": "section",
            "parent_id": sthana_id,
            "content": book_content,
            "metadata": {"title": "Nidana Sthana Introduction"}
        })

    # Link sequential edges (prev_id/next_id)
    link_sequential_edges(chunks)
    
    return chunks

def flush_sections(chunks, buffer, chapter_id, chapter_num, chapter_title):
    if not buffer: return
    
    heading = buffer[0]
    body_lines = buffer[1:]
    
    verse_start, verse_end, title = extract_verse_info(heading)
    content = clean_text("\n".join(buffer))
    
    # Handle orphan headings (## 12.)
    derived_title = False
    if not title and body_lines:
        first_sentence = re.split(r'[\.\?!]', body_lines[0])[0].strip()
        if len(first_sentence) < 100:
            title = first_sentence
            derived_title = True

    # Split long sections
    parts = split_long_section(content)
    for i, part in enumerate(parts):
        suffix = f"_part{i+1}" if len(parts) > 1 else ""
        # Stable ID based on chapter and section title/content
        # Add content hash to ID to ensure uniqueness for sections with same title
        content_hash = str(hash(part))[:8]
        node_id = generate_stable_id(f"ss_{chapter_num}_{title}_{i}_{content_hash}")
        
        chunks.append({
            "id": node_id,
            "level": "section",
            "parent_id": chapter_id,
            "content": part,
            "metadata": {
                "chapter_number": chapter_num,
                "chapter_title": chapter_title,
                "section_title": title + suffix if title else None,
                "derived_title": derived_title,
                "verse_start": verse_start,
                "verse_end": verse_end,
                "has_footnotes": bool(re.search(r'\n\s*\d+\.\s', part)),
                "word_count": len(part.split())
            }
        })

    # VIRTUAL GLOSSARY: Promote header to a glossary stub
    if title and not derived_title and len(title) > 3:
        glossary_id = generate_stable_id(f"glossary_ss_{chapter_num}_{title}")
        chunks.append({
            "id": glossary_id,
            "level": "stub_glossary",
            "parent_id": chapter_id,
            "content": f"Topic: {title}. Surgical/Pathological entry in Susruta Samhita, Chapter {chapter_num}.",
            "metadata": {
                "title": title,
                "source": "shusrut_samhita",
                "context": "promoted_header"
            }
        })

def link_sequential_edges(chunks):
    for i in range(len(chunks)):
        if chunks[i]["level"] == "section":
            ch_num_i = chunks[i]["metadata"].get("chapter_number")
            if ch_num_i is None: continue

            # Prev
            for j in range(i - 1, -1, -1):
                if chunks[j]["level"] == "section" and chunks[j]["metadata"].get("chapter_number") == ch_num_i:
                    chunks[i]["prev_id"] = chunks[j]["id"]
                    break
            # Next
            for j in range(i + 1, len(chunks)):
                if chunks[j]["level"] == "section" and chunks[j]["metadata"].get("chapter_number") == ch_num_i:
                    chunks[i]["next_id"] = chunks[j]["id"]
                    break
