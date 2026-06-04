import re
import os
import json
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

class AyurvedaRouter:
    """
    Router for Ayurveda RAG queries.
    Responsible for pre-processing queries to determine routing mode, 
    detecting language (Sanskrit/English), parsing citations, and classifying intent.
    Now supports LLM-assisted high-precision routing.
    """

    # Regex patterns for direct citations
    PATTERNS = {
        'CS': r'\bCS\s+(Sutra|Ni|Sha|Chi|Vi|Ind|Ka|Sid)\s+(\d+)(?:\.(\d+))?\b',
        'SS': r'\bSS\s+(Su|Ni|Sha|Chi|Ka|Utt)\s+(\d+)(?:\.(\d+))?\b',
        'AH': r'\bAH\s+(Su|Sha|Ni|Chi|Ka|Utt)\s+(\d+)\b'
    }

    TREATISE_MAP = {
        'CS': 'charak_samhita',
        'SS': 'shusrut_samhita',
        'AH': 'astanga_hridaya'
    }

    def __init__(self, llm_client: Optional[genai.Client] = None):
        self.llm_client = llm_client
        self.model_id = 'gemini-2.5-flash-lite'

    def detect_language(self, query: str) -> str:
        if re.search(r'[\u0900-\u097F]', query):
            return 'sanskrit'
        iast_chars = r'[āīūṛṝḷḹṅñṭḍṇśṣḥṃĀĪŪṚṜḶḸṄÑṬḌṆŚṢḤṂ]'
        if re.search(iast_chars, query):
            return 'sanskrit'
        return 'english'

    def detect_citation(self, query: str) -> Optional[Dict[str, Any]]:
        for code, pattern in self.PATTERNS.items():
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                sthana_abbr = match.group(1)
                chapter = match.group(2)
                verse = match.group(3) if len(match.groups()) > 2 and match.group(3) else None
                return {
                    "treatise": self.TREATISE_MAP[code.upper()],
                    "sthana_abbr": sthana_abbr,
                    "chapter": int(chapter),
                    "verse": int(verse) if verse else None
                }
        return None

    def classify_intent_heuristic(self, query: str) -> str:
        query_lower = query.lower()
        if any(k in query_lower for k in ["verse", "sloka", "shloka", "number", "cite"]) or self.detect_citation(query):
            return "Sloka"
        
        intent_map = {
            "Chikitsa": ["treatment", "cure", "medicine", "chikitsa", "therapy", "remedy", "management", "prevention", "formulation"],
            "Nidana": ["cause", "etiology", "diagnosis", "diagnose", "nidana", "origin", "symptoms", "sign", "features", "jvara"],
            "Sharira": ["anatomy", "body", "sharira", "structure", "organ", "physiology", "tissue", "dhatu", "constitution"],
            "Sutra": ["basic", "principle", "sutra", "foundation", "concept", "philosophy", "logic", "definition"]
        }
        for intent, keywords in intent_map.items():
            if any(k in query_lower for k in keywords):
                return intent
        return "General"

    def classify_intent_llm(self, query: str) -> Dict[str, Any]:
        """Uses Gemini to perform high-precision query analysis and clinical entity detection."""
        if not self.llm_client:
            return {"intent": self.classify_intent_heuristic(query), "technical_terms": []}

        prompt = f"""
        Analyze this Ayurveda query for high-precision retrieval routing: "{query}"
        
        Return a JSON object with:
        1. "intent": One of [Sutra, Nidana, Sharira, Chikitsa, Sloka, General].
        2. "clinical_entities": List of specific Diseases, Plants, or Formulations found in the query (e.g., ["Arsha", "Haritaki"]).
        3. "routing_directive": If specific clinical entities are present, output "MANDATORY_GRAPH_LOOKUP". Otherwise "VECTOR_SEARCH".
        4. "technical_terms": List of 1-2 CORE Sanskrit technical terms for search expansion.
        5. "treatise_preference": "charak_samhita", "shusrut_samhita", "astanga_hridaya", or null.
        
        Example: "How to treat fever?" -> {{"intent": "Chikitsa", "clinical_entities": ["Jvara"], "routing_directive": "MANDATORY_GRAPH_LOOKUP", "technical_terms": ["Jvara"], "treatise_preference": null}}
        """
        
        try:
            response = self.llm_client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text)
        except:
            return {"intent": self.classify_intent_heuristic(query), "technical_terms": [], "treatise_preference": None}


    def route(self, query: str) -> Dict[str, Any]:
        language = self.detect_language(query)
        citation = self.detect_citation(query)
        
        # High-Precision LLM Route
        llm_analysis = self.classify_intent_llm(query)
        intent = llm_analysis.get("intent", "General")
        technical_terms = llm_analysis.get("technical_terms", [])
        treatise_hint = llm_analysis.get("treatise_preference")
        clinical_entities = llm_analysis.get("clinical_entities", [])
        routing_directive = llm_analysis.get("routing_directive", "VECTOR_SEARCH")

        # Heuristic fallback for treatise if LLM missed it
        if not treatise_hint:
            ql = query.lower()
            if "charak" in ql: treatise_hint = "charak_samhita"
            elif "susruta" in ql or "shusrut" in ql: treatise_hint = "shusrut_samhita"
            elif "astanga" in ql: treatise_hint = "astanga_hridaya"

        mode = "FALLBACK"
        hints = "General scholarly inquiry."
        
        if citation:
            mode = "DIRECT"
            treatise_hint = citation["treatise"]
            hints = f"DIRECT MANUSCRIPT MATCH: Priority access to {treatise_hint} ({citation['sthana_abbr']} {citation['chapter']})."
        elif routing_directive == "MANDATORY_GRAPH_LOOKUP":
            mode = "GUIDED"
            hints = f"CLINICAL GUIDED SEARCH: Mandatory Graph Lookup for {', '.join(clinical_entities)}. Focus on {intent} contexts."
        elif intent != "General" or language == "sanskrit" or treatise_hint or technical_terms:
            mode = "GUIDED"
            hints = f"GUIDED SCHOLARLY SEARCH: Focus on {intent} contexts. Potential technical mappings: {', '.join(technical_terms)}."
            
        return {
            "mode": mode,
            "intent": intent,
            "language": language,
            "treatise_hint": treatise_hint,
            "citation_params": citation,
            "technical_terms": technical_terms,
            "clinical_entities": clinical_entities,
            "routing_directive": routing_directive,
            "hints": hints
        }

import json # Ensure json is imported

