import re
import html
from typing import List, Dict, Optional

def is_devanagari(text: str) -> bool:
    """Detects if a string is primarily Devanagari."""
    if not text:
        return False
    devanagari_chars = len(re.findall(r'[\u0900-\u097F]', text))
    total_chars = len(text.strip())
    if total_chars == 0:
        return False
    return (devanagari_chars / total_chars) > 0.4

def extract_verse_numbers(text: str) -> Dict[str, Optional[float]]:
    """Extracts verse range from text like '4 - 4.5' or '7.5'."""
    pattern = r'(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?'
    match = re.search(pattern, text)
    if match:
        start = float(match.group(1))
        end = float(match.group(2)) if match.group(2) else start
        return {"verse_start": start, "verse_end": end}
    return {"verse_start": None, "verse_end": None}

def clean_content(content: List[str]) -> str:
    """Cleans up content by stripping code fences and decoding HTML entities."""
    text = "\n".join(content)
    text = re.sub(r'```', '', text)
    return html.unescape(text).strip()
