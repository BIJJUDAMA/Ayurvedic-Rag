import re
import html
from .base import BaseCleaner

class MarkdownCleaner(BaseCleaner):
    def __init__(self):
        super().__init__()
        # Patterns to preserve (Useful abbreviations, citations, references)
        self.preservation_patterns = [
            r'S\.S\.[IVXLCi]+(\.[0-9]+)*', # S.S.II, S.S.i.1 etc
            r'C\.S\.[IVXLC]+(\.[0-9]+)*',   # C.S.I, C.S.V etc
            r'V\.V\.[IVXLC]+(\.[0-9]+)*',   # V.V.III
            r'[A-Z]\.[A-Z]\.[A-Z]\.',       # M.B.B.S, F.R.C.S
        ]

    def clean(self, content: str) -> str:
        text = self.normalize_unicode(content)
        
        # 1. Decode HTML entities
        text = html.unescape(text)
        
        # 2. Filter OCR Base64 images (more robust regex)
        text = re.sub(r'!\[.*?\]\(data:image\/.*?;base64,.*?\)', '', text, flags=re.DOTALL)
        
        # 3. Remove metadata separators and horizontal rules
        text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^={3,}$', '', text, flags=re.MULTILINE)
        
        # 4. Remove common OCR "junk" lines
        # Target lines that are purely punctuation or non-meaningful symbols
        # We use a negative lookahead to ensure we don't hit headers (##) or citations (S.S.)
        text = re.sub(r'^(?![#\s])[^\w\s]{5,}$', '', text, flags=re.MULTILINE)
        
        # 5. Fix common encoding/OCR artifacts
        text = text.replace('Ãna', 'āna')
        text = text.replace('Ã', 'ā')
        text = text.replace('Sushrut', 'Susruta') # Standardize spelling
        
        # 6. Collapse excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
