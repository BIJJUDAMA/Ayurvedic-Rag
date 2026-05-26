import abc
import unicodedata

class BaseCleaner(abc.ABC):
    """Base class for all treatise-specific cleaning strategies."""
    
    def normalize_unicode(self, text: str) -> str:
        """Apply NFC normalization for consistent diacritics."""
        if not text:
            return ""
        return unicodedata.normalize('NFC', text)

    @abc.abstractmethod
    def clean(self, content: str) -> str:
        """Clean the raw content string."""
        pass
