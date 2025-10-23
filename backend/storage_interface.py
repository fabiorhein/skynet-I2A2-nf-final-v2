"""Storage interface defining the contract for document storage backends."""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, TypedDict


class PaginatedResponse(TypedDict):
    """Standard response format for paginated queries."""
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int


class StorageError(Exception):
    """Base class for storage-related errors."""
    pass


class StorageInterface(ABC):
    """Abstract base class defining storage backend interface."""

    @abstractmethod
    def save_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Save a document record. Returns the saved record with generated id."""
        pass

    @abstractmethod
    def get_fiscal_documents(
        self,
        filters: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResponse:
        """Return paginated list of fiscal documents with total count."""
        pass

    @abstractmethod
    def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        """Get history events for a document."""
        pass

    @abstractmethod
    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save a history event. Returns the saved event."""
        pass

    def load_documents(self) -> List[Dict[str, Any]]:
        """Backward compatibility method: loads all documents.
        
        WARNING: This method is deprecated and will be removed.
        Use get_fiscal_documents() instead for proper pagination.
        """
        result = self.get_fiscal_documents(page=1, page_size=1000)
        return result['items']