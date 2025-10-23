"""Supabase storage backend implementation.

Uses Supabase REST API to store and query documents. Implements the StorageInterface.
"""
from typing import Dict, Any, List, Optional
import requests
from .storage_interface import StorageInterface, PaginatedResponse, StorageError


class SupabaseStorageError(StorageError):
    """Supabase-specific storage errors."""
    pass


class SupabaseStorage(StorageInterface):
    """Supabase storage implementation using REST API."""

    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key

    def _headers(self) -> Dict[str, str]:
        return {
            'Content-Type': 'application/json',
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}'
        }

    def _table_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _handle_response(self, r: requests.Response) -> Any:
        try:
            r.raise_for_status()
        except Exception as e:
            try:
                body = r.json()
            except Exception:
                body = r.text
            raise SupabaseStorageError(f"Request failed: {e}; body={body}")
        try:
            return r.json()
        except Exception:
            return r.text

    def save_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Save a fiscal document. Returns the saved record."""
        # Copy the record to avoid modifying the original
        db_record = record.copy()
        
        # Move raw_text to top level if it's in extracted_data 
        if 'extracted_data' in db_record and isinstance(db_record['extracted_data'], dict):
            if 'raw_text' in db_record['extracted_data']:
                db_record['raw_text'] = db_record['extracted_data'].pop('raw_text')

        # Check if raw_text is directly in the record
        if 'raw_text' not in db_record and 'raw_text' in record:
            db_record['raw_text'] = record['raw_text']

        url = self._table_url('fiscal_documents')
        r = requests.post(url, json=db_record, headers=self._headers())
        return self._handle_response(r)

    def get_fiscal_documents(
        self,
        filters: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResponse:
        """Return paginated fiscal documents with total count."""
        url = self._table_url('fiscal_documents')
        offset = (page - 1) * page_size

        # Build query params
        params: Dict[str, Any] = {'select': '*', 'limit': page_size, 'offset': offset}
        if filters:
            for k, v in filters.items():
                if v is None or v == '':
                    continue
                # ilike for case-insensitive partial match
                params[k] = f'ilike.*{v}*'

        # Get documents for current page
        r = requests.get(url, headers=self._headers(), params=params)
        items = self._handle_response(r)
        if not isinstance(items, list):
            items = [items] if items else []

        # Get total count using COUNT query
        count_params = {'select': 'id', 'count': 'exact'}
        if filters:
            count_params.update({k: v for k, v in params.items() if k not in ['select', 'limit', 'offset']})
        
        r = requests.get(
            url,
            headers={**self._headers(), 'Prefer': 'count=exact'},
            params=count_params
        )
        total = int(r.headers.get('Content-Range', '0-0/0').split('/')[-1])

        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size
        }

    def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        """Get history events for a document."""
        url = self._table_url('document_history')
        params = {
            'select': '*',
            'fiscal_document_id': f'eq.{fiscal_document_id}',
            'order': 'created_at.desc'
        }
        r = requests.get(url, headers=self._headers(), params=params)
        result = self._handle_response(r)
        return result if isinstance(result, list) else []

    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save a history event."""
        url = self._table_url('document_history')
        r = requests.post(url, json=event, headers=self._headers())
        return self._handle_response(r)

    # Additional Supabase-specific methods
    def upsert_fiscal_document(self, record: Dict[str, Any], conflict_target: str = 'id') -> Dict[str, Any]:
        """Upsert a document using POST with ?on_conflict."""
        url = self._table_url('fiscal_documents') + f"?on_conflict={conflict_target}"
        r = requests.post(url, json=record, headers=self._headers())
        return self._handle_response(r)

    def get_fiscal_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single document by ID."""
        url = self._table_url('fiscal_documents')
        params = {'select': '*', 'id': f'eq.{doc_id}'}
        r = requests.get(url, headers=self._headers(), params=params)
        result = self._handle_response(r)
        if isinstance(result, list):
            return result[0] if result else None
        return result

    def insert_analysis(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Save an analysis record."""
        url = self._table_url('analyses')
        r = requests.post(url, json=record, headers=self._headers())
        return self._handle_response(r)
