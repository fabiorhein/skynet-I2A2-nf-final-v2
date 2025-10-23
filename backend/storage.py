"""Local JSON storage implementation of StorageInterface."""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, UTC
from .storage_interface import StorageInterface, PaginatedResponse, StorageError


class LocalStorageError(StorageError):
    """Local storage specific errors."""
    pass


class LocalJSONStorage(StorageInterface):
    """Local JSON file storage implementation."""

    def __init__(self, data_dir: str = 'data'):
        self.data_dir = Path(data_dir)
        self.docs_path = self.data_dir / 'processed_documents.json'
        self.history_path = self.data_dir / 'document_history.json'

    def _ensure_dir(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_dir()
        docs = self._load_docs()
        
        # ensure id and timestamps
        if 'id' not in record:
            record['id'] = str(uuid.uuid4())
        if 'created_at' not in record:
            record['created_at'] = datetime.now(UTC).isoformat()
            
        docs.append(record)
        self.docs_path.write_text(
            json.dumps(docs, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        return record

    def get_fiscal_documents(
        self,
        filters: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResponse:
        docs = self._load_docs()
        
        if filters:
            docs = [d for d in docs if self._matches_filters(d, filters)]
            
        total = len(docs)
        start = (page - 1) * page_size
        end = start + page_size
        
        return {
            'items': docs[start:end],
            'total': total,
            'page': page,
            'page_size': page_size
        }

    def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        events = self._load_history()
        return [
            e for e in events
            if e.get('fiscal_document_id') == fiscal_document_id
        ]

    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_dir()
        events = self._load_history()
        
        if 'id' not in event:
            event['id'] = str(uuid.uuid4())
        if 'created_at' not in event:
            event['created_at'] = datetime.now(UTC).isoformat()
            
        events.append(event)
        self.history_path.write_text(
            json.dumps(events, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        return event

    def _load_docs(self) -> List[Dict[str, Any]]:
        if not self.docs_path.exists():
            return []
        try:
            return json.loads(self.docs_path.read_text(encoding='utf-8'))
        except Exception as e:
            raise LocalStorageError(f"Failed to load documents: {e}")

    def _load_history(self) -> List[Dict[str, Any]]:
        if not self.history_path.exists():
            return []
        try:
            return json.loads(self.history_path.read_text(encoding='utf-8'))
        except Exception as e:
            raise LocalStorageError(f"Failed to load history: {e}")

    def _matches_filters(self, doc: Dict[str, Any], filters: Dict[str, str]) -> bool:
        """Check if document matches all filters."""
        for k, v in filters.items():
            if not v:
                continue
            
            # Special handling for common filter fields
            if k == 'document_number':
                # Check numero in parsed or document_number directly
                val = doc.get('document_number') or (doc.get('parsed') or {}).get('numero')
                if val is None:
                    return False
                if v.lower() not in str(val).lower():
                    return False
                continue
                
            if k == 'issuer_cnpj':
                # Check emitente.cnpj in parsed or issuer_cnpj directly
                val = doc.get('issuer_cnpj') or (doc.get('parsed') or {}).get('emitente', {}).get('cnpj')
                if val is None:
                    return False
                if v.lower() not in str(val).lower():
                    return False
                continue
                
            # Default field lookup
            val = doc.get(k)
            if val is None and 'parsed' in doc:
                val = (doc['parsed'] or {}).get(k)
            if val is None and 'extracted_data' in doc:
                val = (doc['extracted_data'] or {}).get(k)
            if val is None:
                return False
            if v.lower() not in str(val).lower():
                return False
        return True


# Create a default instance for backward compatibility
STORAGE_PATH = Path('data') / 'processed_documents.json'
_default = LocalJSONStorage()

# For backward compatibility, expose default instance methods
save_document = _default.save_document
load_documents = _default.load_documents
list_documents = lambda **kwargs: _default.get_fiscal_documents(**kwargs)
save_history = _default.save_history
load_history = _default.get_document_history


def _ensure_dir():
    """Ensure data directory exists."""
    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)


def save_document(record: Dict[str, Any]):
    _ensure_dir()
    arr = []
    if STORAGE_PATH.exists():
        try:
            arr = json.loads(STORAGE_PATH.read_text(encoding='utf-8'))
        except Exception:
            arr = []
    # ensure an id and created_at
    if 'id' not in record:
        record['id'] = str(uuid.uuid4())
    arr.append(record)
    STORAGE_PATH.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding='utf-8')
    return record['id']


def load_documents() -> List[Dict[str, Any]]:
    _ensure_dir()
    if not STORAGE_PATH.exists():
        return []
    try:
        return json.loads(STORAGE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return []


def list_documents(filters: dict = None, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """Return paginated documents and total count. Filters: issuer_cnpj or document_number partial match."""
    docs = load_documents()
    if filters:
        def match(d):
            for k, v in (filters.items() if filters else []):
                if not v:
                    continue
                # support nested parsed fields
                val = d.get(k) or (d.get('parsed') or {}).get(k) or (d.get('extracted_data') or {}).get(k)
                if val is None:
                    return False
                if v.lower() not in str(val).lower():
                    return False
            return True
        docs = [d for d in docs if match(d)]
    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size
    return {'total': total, 'items': docs[start:end], 'page': page, 'page_size': page_size}


HISTORY_PATH = Path('data') / 'document_history.json'


def _ensure_history():
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)


def save_history(event: Dict[str, Any]):
    _ensure_history()
    arr = []
    if HISTORY_PATH.exists():
        try:
            arr = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
        except Exception:
            arr = []
    if 'id' not in event:
        event['id'] = str(uuid.uuid4())
    arr.append(event)
    HISTORY_PATH.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding='utf-8')
    return event['id']


def load_history(fiscal_document_id: str = None) -> List[Dict[str, Any]]:
    _ensure_history()
    if not HISTORY_PATH.exists():
        return []
    try:
        arr = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
    except Exception:
        return []
    if fiscal_document_id:
        return [a for a in arr if a.get('fiscal_document_id') == fiscal_document_id]
    return arr
