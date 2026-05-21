import re
import urllib.parse

class SanskritNormalizer:
    """Handles IAST normalization and rule-based stemming for Ayurvedic Sanskrit."""
    
    @staticmethod
    def normalize_iast(text: str) -> str:
        """Map IAST diacritics to plain ASCII and handle common transliteration variants."""
        mapping = {
            'ā': 'a', 'ī': 'i', 'ū': 'u', 'ṛ': 'ri', 'ṝ': 'ri', 'ḷ': 'l',
            'ṅ': 'n', 'ñ': 'n', 'ṭ': 't', 'ḍ': 'd', 'ṇ': 'n', 'ś': 'sh', 
            'ṣ': 'sh', 'ḥ': 'h', 'ṃ': 'm', 'm̐': 'm'
        }
        text = text.lower()
        for char, replacement in mapping.items():
            text = text.replace(char, replacement)
        
        # Handle common phonetic overlaps
        text = text.replace('shusruta', 'susruta')
        text = text.replace('sushruta', 'susruta')
        text = text.replace('chardi', 'chardi')
        return text

    @staticmethod
    def stem(word: str) -> str:
        """Rule-based stemmer for common Sanskrit Vibhakti (declension) suffixes."""
        if len(word) < 4: return word
        
        # Suffixes to strip (ordered by length descending)
        suffixes = [
            'asya', 'anam', 'ebhyah', 'esu', 'ebhih', 'ena', 'aya', 'at', 'au', 'am', 'e', 'h', 'm'
        ]
        
        for suffix in suffixes:
            if word.endswith(suffix):
                stemmed = word[:-len(suffix)]
                if len(stemmed) >= 3:
                    return stemmed
        return word
