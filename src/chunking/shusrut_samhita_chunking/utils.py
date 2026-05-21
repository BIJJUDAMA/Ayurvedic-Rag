import re
import html
from typing import List, Dict, Optional, Tuple

def is_indological_truths(text: str) -> bool:
    return text.strip() == "## Indological Truths"

def is_citation_marker(text: str) -> bool:
    return bool(re.match(r'^## S\.S\.\s*II\.\s*\d+', text.strip()))

def is_base64_image(line: str) -> bool:
    return "data:image/png;base64," in line

def clean_text(text: str) -> str:
    """Basic cleaning: HTML entities and whitespace."""
    return html.unescape(text).strip()

def extract_verse_info(heading: str) -> Tuple[Optional[float], Optional[float], str]:
    """
    Extracts verse_start, verse_end, and title from headings like:
    '## 14/2, 15. Udana Vayu' -> 14.2, 15.0, 'Udana Vayu'
    '16, 17/1. Samãna Vãyu' -> 16.0, 17.1, 'Samãna Vãyu'
    '## 26-29 Effects of...' -> 26.0, 29.0, 'Effects of...'
    """
    # Optional ## prefix, then optional numbers, then title
    # Supports: 14/2, 15 | 26-29 | 11. | 5-7. | 16, 17/1.
    range_pattern = r'^(?:##\s*)?(?:(\d+(?:[/\.]\d+)?)(?:\s*[-,\s]+\s*(\d+(?:[/\.]\d+)?))?\.?\s*)?(.*)'
    match = re.match(range_pattern, heading.strip())
    if match:
        start_raw = match.group(1)
        end_raw = match.group(2)
        title = match.group(3).strip()
        
        def parse_val(v):
            if not v: return None
            return float(v.replace('/', '.'))
        
        start = parse_val(start_raw)
        end = parse_val(end_raw) if end_raw else start
        
        # If we have a start number, it's a good sign it's a heading
        return start, end, title
    return None, None, heading.replace('##', '').strip()

def get_chapter_title_from_intro(chapter_num: int) -> str:
    """
    Mapping based on the Introduction text provided in the strategy.
    """
    mapping = {
        1: "Diagnosis of Vatika Diseases",
        2: "Diagnosis of Piles",
        3: "Diagnosis of Urinary Calculi",
        4: "Diagnosis of Fistula-in-ano",
        5: "Diagnosis of Skin Diseases",
        6: "Diagnosis of Urinary Abnormalities",
        7: "Diagnosis of Abdominal Enlargements",
        8: "Diagnosis of Abnormal Foetal Presentations",
        9: "Diagnosis of Abscesses",
        10: "Diagnosis of Spreading Cellulitis, Sinuses and Breast Diseases",
        11: "Diagnosis of Glandular Swellings, Cervical Lymphadenopathy, Tumours and Goitres",
        12: "Diagnosis of Scrotal Swellings, Venereal Diseases and Elephantiasis",
        13: "Diagnosis of Minor Diseases",
        14: "Diagnosis of Suka Dosa",
        15: "Diagnosis of Fractures and Dislocations",
        16: "Diagnosis of Oral Diseases"
    }
    return mapping.get(chapter_num, f"Chapter {chapter_num}")

def split_long_section(content: str, max_words: int = 500) -> List[str]:
    """Splits content at natural paragraph breaks if it exceeds max_words."""
    words = content.split()
    if len(words) <= max_words:
        return [content]
    
    # Split by double newline (paragraphs)
    paragraphs = content.split('\n\n')
    parts = []
    current_part = []
    current_count = 0
    
    for p in paragraphs:
        p_len = len(p.split())
        if current_count + p_len > max_words and current_part:
            parts.append('\n\n'.join(current_part))
            current_part = [p]
            current_count = p_len
        else:
            current_part.append(p)
            current_count += p_len
            
    if current_part:
        parts.append('\n\n'.join(current_part))
    return parts
