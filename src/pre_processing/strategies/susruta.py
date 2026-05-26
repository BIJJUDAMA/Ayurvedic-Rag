import re
from .markdown_base import MarkdownCleaner

class SusrutaCleaner(MarkdownCleaner):
    def clean(self, content: str) -> str:
        text = super().clean(content)
        
        # 1. Remove repeating institutional/author headers if they dominate a block
        boilerplate = [
            r'## Indological Truths',
            r'Indological Truths',
            r'Singhal, G\.D',
            r'PROF\. K\. N\. UDUPA',
            r'Director, Institute of Medical Sciences',
            r'Banaras Hindu University',
            r'Varanasi-5 \(INDIA\)',
            r'Thy right is to work only; but never to its fruits.*?\.', 
            r'SUGGESTED RESEARCH PROBLEMS.*',
            r'SEND US YOUR SUGGESTIONS.*',
            r'## S\.S\.II\.\d+',
        ]
        
        for pattern in boilerplate:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

        # 2. Fix OCR artifacts in references
        # Sometimes S.S.IV becomes S.S.TV or S.S. i
        text = re.sub(r'S\.S\.TV', 'S.S.IV', text)
        text = re.sub(r'S\.S\.\s+([IVX])', r'S.S.\1', text) # Remove space in S.S. IV

        # 3. Handle abbreviations table noise
        # Preserve the core info but remove the dots often used as leader lines
        # e.g. "Manu-Smrti ••...•••" -> "Manu-Smrti"
        text = re.sub(r'([a-zA-Z\s])([\.•]{3,})', r'\1 ', text)
        
        return text.strip()
