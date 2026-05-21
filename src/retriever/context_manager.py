from typing import Dict, Any, List, Optional
from qdrant_client import QdrantClient

class AyurvedaContextManager:
    def __init__(self, client: QdrantClient, collection_name: str):
        self.client = client
        self.collection_name = collection_name

    def get_breadcrumb(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Recursively fetch the hierarchy path from child to root."""
        breadcrumb = []
        current_parent_id = payload.get("parent_id")
        
        while current_parent_id:
            try:
                res = self.client.retrieve(collection_name=self.collection_name, ids=[current_parent_id])
                if not res:
                    break
                parent_payload = res[0].payload
                breadcrumb.append({
                    "level": parent_payload.get("level"),
                    "title": parent_payload.get("title") or parent_payload.get("chapter_title") or parent_payload.get("section_title"),
                    "content": parent_payload.get("content", "")[:200] # Snippet for context
                })
                current_parent_id = parent_payload.get("parent_id")
            except Exception as e:
                print(f"Breadcrumb error: {e}")
                break
        
        return breadcrumb[::-1] # Return root -> child

    def get_contiguous_block(self, payload: Dict[str, Any], window: int = 1) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch a window of preceding and succeeding nodes."""
        block = {"prev": [], "next": []}
        
        # Fetch Preceding
        current_prev_id = payload.get("prev_id")
        for _ in range(window):
            if not current_prev_id: break
            try:
                res = self.client.retrieve(collection_name=self.collection_name, ids=[current_prev_id])
                if not res: break
                block["prev"].insert(0, res[0].payload)
                current_prev_id = res[0].payload.get("prev_id")
            except: break
            
        # Fetch Succeeding
        current_next_id = payload.get("next_id")
        for _ in range(window):
            if not current_next_id: break
            try:
                res = self.client.retrieve(collection_name=self.collection_name, ids=[current_next_id])
                if not res: break
                block["next"].append(res[0].payload)
                current_next_id = res[0].payload.get("next_id")
            except: break
            
        return block

    def expand_context(self, doc_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Unified context expansion: breadcrumbs + contiguous verses."""
        return {
            "breadcrumb": self.get_breadcrumb(payload),
            "neighbors": self.get_contiguous_block(payload, window=1)
        }
