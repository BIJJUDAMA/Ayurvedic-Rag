import re
from .markdown_base import MarkdownCleaner

class AshtangaCleaner(MarkdownCleaner):
    """
    Specialized cleaner for Ashtanga Hridaya.
    Handles trilingual text patterns and specific OCR artifacts.
    """
    
    def clean(self, content: str) -> str:
        # 1. Start with base Markdown cleaning
        text = super().clean(content)
        
        # 2. OCR Restoration / Standardization
        # Standardizing spelling of Vata
        text = re.sub(r'\bVaata\b', 'Vata', text)
        
        # Adding Sanskrit context to 'vitiation'
        # Using a regex to avoid double-replacing if it's already there
        text = re.sub(r'\bvitiation\b(?!\s+\(dosa-vaishamya\))', 'vitiation (dosa-vaishamya)', text)
        
        # 3. Noise Stripping
        # Remove bracketed notes like [1], [Note: ...], etc.
        text = re.sub(r'\[.*?\]', '', text)
        
        # Strip filename leakage
        text = text.replace('astanga-hridaya.md', '')
        
        # Remove (English Translation) labels
        text = re.sub(r'\(English Translation\)', '', text, flags=re.IGNORECASE)
        
        # 4. Final Whitespace Normalization
        # Collapse excessive newlines (already handled by super().clean but reinforcing)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Collapse excessive spaces within a line
        text = re.sub(r'[ \t]{2,}', ' ', text)
        
        return text.strip()
