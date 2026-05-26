import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class IntegrityMonitor:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            max_features=1000,
            token_pattern=r'(?u)\b\w+\b' # Include words with digits/accents
        )

    def measure_loss(self, raw_text: str, processed_text: str):
        """
        Compares raw and processed text using TF-IDF vectors.
        Returns a retention score and character counts.
        """
        if not raw_text or not processed_text:
            return {
                "retention_score": 0.0,
                "raw_chars": len(raw_text),
                "processed_chars": len(processed_text),
                "loss_percentage": 100.0
            }

        # Calculate character counts
        raw_len = len(raw_text)
        proc_len = len(processed_text)
        loss_pct = ((raw_len - proc_len) / raw_len) * 100 if raw_len > 0 else 0

        try:
            # Vectorize both
            tfidf_matrix = self.vectorizer.fit_transform([raw_text, processed_text])
            
            # Calculate Cosine Similarity
            # This measures how much of the "meaningful" vocabulary was preserved
            score = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        except Exception as e:
            # If text is too small or vectorization fails
            score = 1.0 if proc_len > 0 else 0.0

        return {
            "retention_score": round(float(score), 4),
            "raw_chars": raw_len,
            "processed_chars": proc_len,
            "loss_percentage": round(loss_pct, 2)
        }

    def check_devanagari_loss(self, raw_text: str, processed_text: str) -> bool:
        """
        Checks if Devanagari characters were significantly lost.
        Returns True if a large block of Devanagari disappeared.
        """
        def count_devanagari(t):
            return len([c for c in t if '\u0900' <= c <= '\u097F'])
        
        raw_deva = count_devanagari(raw_text)
        proc_deva = count_devanagari(processed_text)
        
        if raw_deva > 0 and proc_deva / raw_deva < 0.95:
            return True # More than 5% loss of Devanagari is suspicious
        return False
