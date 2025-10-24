"""Tests for StorageInterface implementation validation."""
import sys
import pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from typing import Dict, Any, List, Optional
from backend.storage import StorageInterface, PaginatedResponse
import pytest


class DummyStorage(StorageInterface):
    """Minimal implementation of StorageInterface for testing."""

    def save_document(self, record):
        return record

    def get_fiscal_documents(self, filters=None, page=1, page_size=50):
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}

    def get_document_history(self, fiscal_document_id):
        return []

    def save_history(self, event):
        return event


def test_interface_implementation():
    """Test that a class implementing all methods can be instantiated."""
    storage = DummyStorage()
    assert isinstance(storage, StorageInterface)


class BrokenStorage(StorageInterface):
    """Incomplete implementation missing required methods."""
    pass


def test_incomplete_implementation():
    """Test that an incomplete implementation raises TypeError."""
    class IncompleteStorage(StorageInterface):
        def save_fiscal_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
            pass
            
        def get_fiscal_documents(
            self,
            filters: Optional[Dict[str, str]] = None,
            page: int = 1,
            page_size: int = 50
        ) -> PaginatedResponse:
            pass
            
        # Faltando implementar get_document_history
        # def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        #     pass
    
    # Verifica se a classe abstrata está sendo implementada corretamente
    with pytest.raises((TypeError, NotImplementedError)):
        # Deve lançar TypeError ou NotImplementedError porque faltam métodos abstratos
        storage = IncompleteStorage()
        # Força a verificação de tipo tentando usar o storage
        storage.get_document_history("test")


def test_paginated_response_typing():
    """Test PaginatedResponse type validation."""
    # Valid response
    response: PaginatedResponse = {
        'items': [],
        'total': 0,
        'page': 1,
        'page_size': 50
    }
    assert isinstance(response, dict)
    
    # Would raise type error in a typed environment:
    # response: PaginatedResponse = {'items': []}  # Missing required fields