import re
import json
import os
import uuid
import urllib.parse
from typing import List, Dict, Any, Tuple
from .utils import canonicalize, has_devanagari, devanagari_density, mediawiki_slugify, generate_id
from .config import (
    TYPE_BOTANICAL, TYPE_GLOSSARY, TYPE_CONCEPT, TYPE_PROCEDURAL, 
    TYPE_STHANA, TYPE_CHAPTER, TYPE_SECTION, TYPE_VERSE, TYPE_APPARATUS
)

# Hierarchy Configuration
STHANA_KEYS = [
    "Sutra_Sthana", "Nidana_Sthana", "Vimana_Sthana", 
    "Sharira_Sthana", "Indriya_Sthana", "Chikitsa_Sthana", 
    "Kalpa_Sthana", "Siddhi_Sthana"
]

ADMIN_KEYWORDS = ["Contributors", "Project", "Guidelines", "Preface", "Main_Page", "Donate", "Referencing"]
GLOSSARY_KEYWORDS = ["List_of_herbs", "Botanical", "Glossary"]

def normalize_wiki_title(text: str) -> str:
    """Decode and normalize Wiki titles for consistent matching."""
    decoded = urllib.parse.unquote(text)
    # Replace Wiki underscores and different dash types with spaces
    normalized = decoded.replace("_", " ").replace("–", "-").replace("—", "-")
    return re.sub(r'\s+', ' ', normalized).strip()

class CharakaHierarchyManager:
    def __init__(self, dir_path: str):
        self.dir_path = dir_path
        self.toc_map = {} # normalized_title -> sthana_id
        self.affinity_map = {} # normalized_title -> best_sthana_id
        self.sthana_ids = {k: generate_id(f"sthana_{k.lower()}") for k in STHANA_KEYS}
        self.meta_hub_id = generate_id("charaka_meta_hub")
        self.materia_medica_id = generate_id("charaka_materia_medica")
        self.root_id = generate_id("root_charaka_samhita")

    def _extract_title_from_link(self, link: str) -> str:
        """Helper to extract and normalize a title from various Wiki link formats."""
        if "title=" in link:
            # Extract from query parameter
            slug = link.split("title=")[-1].split("&")[0]
        elif "/wiki/" in link:
            # Extract from path
            slug = link.split("/wiki/")[-1].split("#")[0]
        else:
            # Fallback
            slug = link.split("/")[-1].split("#")[0]
        return normalize_wiki_title(slug)

    def pre_scan(self):
        print("Starting Charaka Link Affinity Pre-scan...")
        if not os.path.exists(self.dir_path): return
        files = [f for f in os.listdir(self.dir_path) if f.endswith(".json")]
        
        # 1. Build ToC from Abstracts
        for filename in files:
            if "Abstracts" in filename:
                sthana_key = None
                norm_filename = normalize_wiki_title(filename)
                for k in STHANA_KEYS:
                    if k.replace("_", " ") in norm_filename:
                        sthana_key = k
                        break
                if sthana_key:
                    try:
                        with open(os.path.join(self.dir_path, filename), "r", encoding="utf-8") as f:
                            data = json.load(f)
                            links = data.get("outgoing_links", [])
                            for link in links:
                                title = self._extract_title_from_link(link)
                                if title and title != "Charaka Samhita":
                                    self.toc_map[title] = self.sthana_ids[sthana_key]
                    except: continue

        # 2. Calculate Affinity for everything else
        for filename in files:
            try:
                path = os.path.join(self.dir_path, filename)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    links = data.get("outgoing_links", [])
                    title = data.get("title", "")
                    norm_title = normalize_wiki_title(title)
                    
                    if any(kw.lower() in filename.lower() or kw.lower() in title.lower() for kw in ADMIN_KEYWORDS):
                        self.affinity_map[norm_title] = self.meta_hub_id
                        continue
                    
                    if any(kw.lower() in filename.lower() or kw.lower() in title.lower() for kw in GLOSSARY_KEYWORDS):
                        self.affinity_map[norm_title] = self.materia_medica_id
                        continue

                    if norm_title in self.toc_map:
                        self.affinity_map[norm_title] = self.toc_map[norm_title]
                        continue

                    # Link Affinity Scoring (Higher weights for direct Sthana links)
                    scores = {sid: 0 for sid in self.sthana_ids.values()}
                    for link in links:
                        link_title = self._extract_title_from_link(link)
                        if not link_title: continue
                        
                        # Direct Sthana Link (Massive weight)
                        for k, sid in self.sthana_ids.items():
                            if k.replace("_", " ") in link_title:
                                scores[sid] += 10
                        
                        # Neighbor Link (Strong weight)
                        if link_title in self.toc_map:
                            scores[self.toc_map[link_title]] += 2
                    
                    if not scores:
                        self.affinity_map[norm_title] = self.root_id
                        continue

                    best_sthana = max(scores, key=scores.get)
                    if scores[best_sthana] > 0:
                        self.affinity_map[norm_title] = best_sthana
                    else:
                        self.affinity_map[norm_title] = self.root_id
            except: continue

    def get_parent(self, title: str) -> str:
        norm_title = normalize_wiki_title(title)
        return self.affinity_map.get(norm_title, self.root_id)

class CharakaParser:
    def __init__(self, registry, dir_path: str = None):
        self.registry = registry
        self.dir_path = dir_path or os.path.join("books", "charak_samhita")
        self.hierarchy = CharakaHierarchyManager(self.dir_path)
        self.hierarchy.pre_scan()
        self.treatise_root_id = self.hierarchy.root_id

    def classify_document(self, data: Dict[str, Any]) -> str:
        text = data.get("text", "")
        title = data.get("title", "")
        html = data.get("html", "")
        
        if (text.startswith("Preamble of") and "Contents" in text) or "Abstracts -" in title:
            return TYPE_STHANA
        
        if len(text) > 40000 and has_devanagari(text):
            return TYPE_CHAPTER
        
        if "Herb database" in html or re.match(r'^[A-Z][a-z]+ [a-z]+', text):
            if len(text) < 10000:
                 return TYPE_BOTANICAL
        
        if "Panchakarma" in html or ("purvakarma" in text.lower() and "pradhanakarma" in text.lower()):
            return TYPE_PROCEDURAL
            
        if "Contents" in text and len(text) > 5000:
            return TYPE_CONCEPT
            
        if len(text) < 500:
            return TYPE_GLOSSARY
            
        return TYPE_CONCEPT

    def parse(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        doc_type = self.classify_document(data)
        canonical_id = self.registry.register(data["title"], data["url"])
        
        # Use hierarchy manager for parenting based on title
        sthana_parent_id = self.hierarchy.get_parent(data["title"])
        
        chunks = []
        if doc_type == TYPE_BOTANICAL:
            chunks = self.parse_botanical(data, canonical_id, sthana_parent_id)
        elif doc_type == TYPE_GLOSSARY:
            chunks = self.parse_glossary(data, canonical_id, sthana_parent_id)
        elif doc_type == TYPE_STHANA:
            chunks = self.parse_sthana(data, canonical_id)
        elif doc_type == TYPE_CHAPTER:
            chunks = self.parse_chapter(data, canonical_id, sthana_parent_id)
        elif doc_type == TYPE_CONCEPT or doc_type == TYPE_PROCEDURAL:
            chunks = self.parse_article(data, canonical_id, doc_type, sthana_parent_id)
        else:
            chunks = [self.create_chunk(canonical_id, doc_type, data["title"], data["text"], data, parent_id=sthana_parent_id)]

        if len(chunks) > 1:
            for i in range(len(chunks) - 1):
                chunks[i]["next_id"] = chunks[i+1]["id"]
                chunks[i+1]["prev_id"] = chunks[i]["id"]
        
        return chunks

    def create_chunk(self, cid: str, clevel: str, title: str, content: str, data: Dict[str, Any], metadata: Dict[str, Any] = None, parent_id: str = None) -> Dict[str, Any]:
        if metadata is None:
            metadata = {}
        if parent_id is None:
            parent_id = self.treatise_root_id

        # Use a more robust stable ID for chunks
        content_hash = generate_id(content[:100] if content else "empty")
        chunk_id = generate_id(f"{cid}_{clevel}_{title}_{content_hash}")

        return {
            "id": chunk_id,
            "canonical_id": cid,
            "parent_id": parent_id,
            "prev_id": None,
            "next_id": None,
            "level": clevel,
            "title": title,
            "content": content,
            "url": data.get("url", ""),
            "metadata": metadata
        }

    def parse_botanical(self, data: Dict[str, Any], cid: str, sthana_parent_id: str) -> List[Dict[str, Any]]:
        content = data["text"]
        content = re.sub(r'Contents\n.*?\n(?=[A-Z])', '', content, flags=re.DOTALL)
        content = content.split("Send us your suggestions")[0].strip()
        return [self.create_chunk(cid, TYPE_BOTANICAL, data["title"], content, data, parent_id=sthana_parent_id)]

    def parse_glossary(self, data: Dict[str, Any], cid: str, sthana_parent_id: str) -> List[Dict[str, Any]]:
        return [self.create_chunk(cid, TYPE_GLOSSARY, data["title"], data["text"], data, parent_id=sthana_parent_id)]

    def parse_sthana(self, data: Dict[str, Any], cid: str) -> List[Dict[str, Any]]:
        return [self.create_chunk(cid, TYPE_STHANA, data["title"], data["text"], data, parent_id=self.treatise_root_id)]

    def parse_article(self, data: Dict[str, Any], cid: str, doc_type: str, sthana_parent_id: str) -> List[Dict[str, Any]]:
        chunks = []
        text = data["text"]
        title = data["title"]
        
        lede_match = re.search(r'Contents\n\n(.*?)\n\n', text, re.DOTALL)
        if lede_match:
            toc_lines = lede_match.group(1).strip().split('\n')
            section_titles = [re.sub(r'^\d+(\.\d+)*\s+', '', line).strip() for line in toc_lines if re.match(r'^\d+', line)]
            
            if section_titles:
                first_section = section_titles[0]
                lede_end = text.find(f"\n\n{first_section}\n\n")
                if lede_end != -1:
                    lede_content = text[:lede_end].strip()
                    chunks.append(self.create_chunk(cid, doc_type, title, lede_content, data, parent_id=sthana_parent_id))
                    article_root_id = chunks[-1]["id"]
                    text = text[lede_end:].strip()
                
                    for i, st in enumerate(section_titles):
                        next_st = section_titles[i+1] if i+1 < len(section_titles) else None
                        start_idx = text.find(st)
                        if start_idx == -1: continue
                        
                        end_idx = text.find(next_st) if next_st else len(text)
                        section_body = text[start_idx:end_idx].strip()
                        section_content = section_body[len(st):].strip()
                        
                        chunks.append(self.create_chunk(
                            f"{cid}_{mediawiki_slugify(st)}", 
                            TYPE_SECTION, 
                            f"{title} - {st}", 
                            section_content, 
                            data,
                            {"section_title": st, "anchor": mediawiki_slugify(st)},
                            parent_id=article_root_id
                        ))
            else:
                chunks.append(self.create_chunk(cid, doc_type, title, text, data, parent_id=sthana_parent_id))
        else:
            chunks.append(self.create_chunk(cid, doc_type, title, text, data, parent_id=sthana_parent_id))
            
        return chunks

    def parse_chapter(self, data: Dict[str, Any], cid: str, sthana_parent_id: str) -> List[Dict[str, Any]]:
        chunks = []
        text = data["text"]
        title = data["title"]
        
        abstract_match = re.search(r'Abstract\n\n(.*?)\n\nKeywords', text, re.DOTALL)
        if abstract_match:
            abstract_content = abstract_match.group(1).strip()
            chunks.append(self.create_chunk(cid, TYPE_CHAPTER, title, abstract_content, data, parent_id=sthana_parent_id))
            chapter_root_id = chunks[-1]["id"]
        else:
            chunks.append(self.create_chunk(cid, TYPE_CHAPTER, title, f"Chapter: {title}", data, parent_id=sthana_parent_id))
            chapter_root_id = chunks[-1]["id"]

        verse_pattern = re.compile(r'([\u0900-\u097F]{10,}.*?\[(\d+[-–\d,\s]*)\])(?=\n\n|$)', re.DOTALL)
        matches = list(verse_pattern.finditer(text))
        for match in matches:
            verse_content = match.group(1).strip()
            verse_ref = match.group(2).strip()
            sanskrit_parts = re.findall(r'[\u0900-\u097F].*?\|\|\d+\|\|', verse_content, re.DOTALL)
            
            chunks.append(self.create_chunk(
                f"{cid}_verse_{verse_ref}",
                TYPE_VERSE,
                f"{title} Verse {verse_ref}",
                verse_content,
                data,
                {
                    "verse_ref": verse_ref,
                    "sanskrit_count": len(sanskrit_parts),
                    "is_tripartite": "||" in verse_content and "[" in verse_content
                },
                parent_id=chapter_root_id
            ))
        return chunks

    def parse_botanical(self, data: Dict[str, Any], cid: str, sthana_parent_id: str) -> List[Dict[str, Any]]:
        content = data["text"]
        content = re.sub(r'Contents\n.*?\n(?=[A-Z])', '', content, flags=re.DOTALL)
        content = content.split("Send us your suggestions")[0].strip()
        return [self.create_chunk(cid, TYPE_BOTANICAL, data["title"], content, data, parent_id=sthana_parent_id)]

    def parse_glossary(self, data: Dict[str, Any], cid: str, sthana_parent_id: str) -> List[Dict[str, Any]]:
        return [self.create_chunk(cid, TYPE_GLOSSARY, data["title"], data["text"], data, parent_id=sthana_parent_id)]

    def parse_sthana(self, data: Dict[str, Any], cid: str) -> List[Dict[str, Any]]:
        return [self.create_chunk(cid, TYPE_STHANA, data["title"], data["text"], data, parent_id=self.treatise_root_id)]

    def parse_article(self, data: Dict[str, Any], cid: str, doc_type: str, sthana_parent_id: str) -> List[Dict[str, Any]]:
        chunks = []
        text = data["text"]
        title = data["title"]
        
        lede_match = re.search(r'Contents\n\n(.*?)\n\n', text, re.DOTALL)
        if lede_match:
            toc_lines = lede_match.group(1).strip().split('\n')
            section_titles = [re.sub(r'^\d+(\.\d+)*\s+', '', line).strip() for line in toc_lines if re.match(r'^\d+', line)]
            
            if section_titles:
                first_section = section_titles[0]
                lede_end = text.find(f"\n\n{first_section}\n\n")
                if lede_end != -1:
                    lede_content = text[:lede_end].strip()
                    chunks.append(self.create_chunk(cid, doc_type, title, lede_content, data, parent_id=sthana_parent_id))
                    article_root_id = chunks[-1]["id"]
                    text = text[lede_end:].strip()
                
                    for i, st in enumerate(section_titles):
                        next_st = section_titles[i+1] if i+1 < len(section_titles) else None
                        start_idx = text.find(st)
                        if start_idx == -1: continue
                        
                        end_idx = text.find(next_st) if next_st else len(text)
                        section_body = text[start_idx:end_idx].strip()
                        section_content = section_body[len(st):].strip()
                        
                        chunks.append(self.create_chunk(
                            f"{cid}_{mediawiki_slugify(st)}", 
                            TYPE_SECTION, 
                            f"{title} - {st}", 
                            section_content, 
                            data,
                            {"section_title": st, "anchor": mediawiki_slugify(st)},
                            parent_id=article_root_id
                        ))
            else:
                chunks.append(self.create_chunk(cid, doc_type, title, text, data, parent_id=sthana_parent_id))
        else:
            chunks.append(self.create_chunk(cid, doc_type, title, text, data, parent_id=sthana_parent_id))
            
        return chunks

    def parse_chapter(self, data: Dict[str, Any], cid: str, sthana_parent_id: str) -> List[Dict[str, Any]]:
        chunks = []
        text = data["text"]
        title = data["title"]
        
        abstract_match = re.search(r'Abstract\n\n(.*?)\n\nKeywords', text, re.DOTALL)
        if abstract_match:
            abstract_content = abstract_match.group(1).strip()
            chunks.append(self.create_chunk(cid, TYPE_CHAPTER, title, abstract_content, data, parent_id=sthana_parent_id))
            chapter_root_id = chunks[-1]["id"]
        else:
            chunks.append(self.create_chunk(cid, TYPE_CHAPTER, title, f"Chapter: {title}", data, parent_id=sthana_parent_id))
            chapter_root_id = chunks[-1]["id"]

        verse_pattern = re.compile(r'([\u0900-\u097F]{10,}.*?\[(\d+[-–\d,\s]*)\])(?=\n\n|$)', re.DOTALL)
        matches = list(verse_pattern.finditer(text))
        for match in matches:
            verse_content = match.group(1).strip()
            verse_ref = match.group(2).strip()
            sanskrit_parts = re.findall(r'[\u0900-\u097F].*?\|\|\d+\|\|', verse_content, re.DOTALL)
            
            chunks.append(self.create_chunk(
                f"{cid}_verse_{verse_ref}",
                TYPE_VERSE,
                f"{title} Verse {verse_ref}",
                verse_content,
                data,
                {
                    "verse_ref": verse_ref,
                    "sanskrit_count": len(sanskrit_parts),
                    "is_tripartite": "||" in verse_content and "[" in verse_content
                },
                parent_id=chapter_root_id
            ))
        return chunks
