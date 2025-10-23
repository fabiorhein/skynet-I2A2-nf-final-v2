"""Common test cases for storage implementations."""
from typing import Any, Dict, List
from backend.storage_interface import StorageInterface
import pytest


class StorageComplianceTests:
    """Test suite to validate storage implementation compliance.
    
    Usage:
        class TestMyStorage(StorageComplianceTests):
            @pytest.fixture
            def storage(self):
                return MyStorage()
    """
    
    @pytest.fixture
    def storage(self) -> StorageInterface:
        """Override this fixture to provide storage implementation to test."""
        raise NotImplementedError
    
    def test_document_crud(self, storage: StorageInterface):
        """Test basic document CRUD operations."""
        # Create
        doc = {
            'file': 'test.xml',
            'parsed': {
                'numero': '123',
                'emitente': {'cnpj': '12345678000195'}
            }
        }
        saved = storage.save_document(doc)
        assert saved
        assert 'id' in saved
        
        # Read (list)
        result = storage.get_fiscal_documents(
            filters={'document_number': '123'}
        )
        assert result['total'] >= 1
        assert len(result['items']) > 0
        
        # Paginate
        page1 = storage.get_fiscal_documents(page=1, page_size=1)
        assert len(page1['items']) <= 1
        
        # History
        if hasattr(storage, 'save_history'):  # Optional capability
            event = {
                'fiscal_document_id': saved['id'],
                'event_type': 'test',
                'event_data': {'note': 'test'}
            }
            saved_event = storage.save_history(event)
            assert saved_event
            assert 'id' in saved_event
            
            history = storage.get_document_history(saved['id'])
            assert len(history) >= 1
    
    def test_filter_validation(self, storage: StorageInterface):
        """Test filter handling."""
        # Empty filters
        result = storage.get_fiscal_documents(filters={})
        assert isinstance(result, dict)
        assert 'items' in result
        assert 'total' in result
        
        # None filters
        result = storage.get_fiscal_documents(filters=None)
        assert isinstance(result, dict)
        assert 'items' in result
        
        # Invalid filter should not raise
        result = storage.get_fiscal_documents(
            filters={'nonexistent_field': 'value'}
        )
        assert isinstance(result, dict)
    
    def test_pagination_validation(self, storage: StorageInterface):
        """Test pagination parameter handling."""
        # Page size
        result = storage.get_fiscal_documents(page_size=1)
        assert len(result['items']) <= 1
        
        # Page number
        result = storage.get_fiscal_documents(page=2, page_size=1)
        assert isinstance(result, dict)
        assert result['page'] == 2
        
        # Invalid page (should handle gracefully)
        result = storage.get_fiscal_documents(page=-1)
        assert isinstance(result, dict)
        
        # Large page size (should handle gracefully)
        result = storage.get_fiscal_documents(page_size=1000000)
        assert isinstance(result, dict)