import re
import json
from .base import BaseCleaner

class CharakaCleaner(BaseCleaner):
    def clean(self, content: str) -> str:
        # 1. Unicode Normalization
        text = self.normalize_unicode(content)
        
        # 2. Remove MediaWiki / SMW artifacts
        # Remove Contents section usually found at start
        text = re.sub(r'Contents\n\n.*?\n\n', '', text, flags=re.DOTALL)
        
        # Remove "Send us your suggestions..." and everything after
        text = re.sub(r'Send us your suggestions.*', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove outgoing links markers if they leaked into text
        text = re.sub(r'https?://charakasamhita\.com\S+', '', text)
        
        # 3. Collapse whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        
        return text

    def process_json(self, raw_json: dict) -> dict:
        """Processes the specific fields in the Charaka JSON."""
        processed = raw_json.copy()
        if "text" in processed:
            processed["text"] = self.clean(processed["text"])
        return processed
