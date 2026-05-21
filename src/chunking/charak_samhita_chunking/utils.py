import re
import uuid
from typing import Optional, List, Dict

def generate_id(text: str) -> str:
    """Generate a stable UUID from a string."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, text))

def canonicalize(text: str) -> str:
    """Canonicalize a title into an ID."""
    return re.sub(r'\s+', '_', text.strip().lower())

def extract_slug(url: str) -> Optional[str]:
    """Extract the title/slug from a MediaWiki URL."""
    match = re.search(r'title=([^&]+)', url)
    if match:
        return match.group(1)
    return None

def mediawiki_slugify(text: str) -> str:
    """Convert a section title into a MediaWiki anchor slug."""
    # MediaWiki replaces spaces with underscores and keeps case
    return text.strip().replace(" ", "_")

def has_devanagari(text: str) -> bool:
    """Detect if text contains Devanagari characters."""
    return bool(re.search(r'[\u0900-\u097F]', text))

def devanagari_density(text: str) -> float:
    """Calculate the density of Devanagari characters in text."""
    if not text:
        return 0.0
    devanagari_chars = len(re.findall(r'[\u0900-\u097F]', text))
    return devanagari_chars / len(text)

class SlugRegistry:
    def __init__(self):
        self.slug_to_id = {}
        self.title_to_id = {}
        self.redlinks = set()

    def register(self, title: str, url: str):
        cid = canonicalize(title)
        self.title_to_id[title] = cid
        slug = extract_slug(url)
        if slug:
            self.slug_to_id[slug] = cid
            # Handle aliases (e.g. Trimarmiya_Siddhi_Adhyaya vs Trimarmiya_Siddhi)
            if "_" in slug:
                self.slug_to_id[slug.replace("_", " ")] = cid
        return cid

    def resolve(self, slug_or_url: str) -> Optional[str]:
        if "redlink=1" in slug_or_url or "action=edit" in slug_or_url:
            return None
        
        slug = extract_slug(slug_or_url) if "http" in slug_or_url else slug_or_url
        if not slug:
            return None
            
        return self.slug_to_id.get(slug)
