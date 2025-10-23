"""Tests for StorageInterface implementation validation."""
import sys
import pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from backend.storage_interface import StorageInterface, PaginatedResponse
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
    with pytest.raises(TypeError):
        BrokenStorage()


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