"""Common test cases for storage implementations."""
from typing import Any, Dict, List
from backend.database import StorageInterface
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
            'document_type': 'NFe',
            'document_number': '123',
            'parsed': {
                'numero': '123',
                'emitente': {'cnpj': '12345678000195'}
            }
        }
        saved = storage.save_fiscal_document(doc)  # Usando save_fiscal_document
        assert saved is not None
        assert 'id' in saved

        # Read (list)
        result = storage.get_fiscal_documents(
            filters={'document_number': '123'}
        )
        assert hasattr(result, 'total'), "Result should be a PaginatedResponse object"
        assert result.total >= 1
        assert any(d.get('id') == saved['id'] for d in result.items) > 0
        
        # Paginate
        page1 = storage.get_fiscal_documents(page=1, page_size=1)
        assert hasattr(page1, 'items'), "PaginatedResponse should have 'items' attribute"
        assert len(page1.items) <= 1, "Should return at most 1 item per page"
        
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
        assert hasattr(result, 'items'), "Result should have 'items' attribute"
        assert hasattr(result, 'total'), "Result should have 'total' attribute"
        assert isinstance(result.items, list), "Items should be a list"
        
        # Invalid filter field
        result = storage.get_fiscal_documents(filters={'invalid': 'value'})
        assert hasattr(result, 'items')
        assert hasattr(result, 'total')
        
        # Valid filter
        # Primeiro salvamos um documento para garantir que temos algo para filtrar
        doc = {
            'file': 'test_filter.xml',
            'document_type': 'NFe',
            'document_number': '12345',
            'parsed': {'numero': '12345'}
        }
        storage.save_fiscal_document(doc)
        
        result = storage.get_fiscal_documents(filters={'document_number': '12345'})
        assert hasattr(result, 'items')
        assert hasattr(result, 'total')
        assert result.total >= 1, "Should find at least one document with number 12345"
    
    def test_pagination_validation(self, storage: StorageInterface):
        """Test pagination parameter handling."""
        # Adiciona alguns documentos de teste
        for i in range(5):
            doc = {
                'file': f'test_pag_{i}.xml',
                'document_type': 'NFe',
                'document_number': str(1000 + i),
                'parsed': {'numero': str(1000 + i)}
            }
            storage.save_fiscal_document(doc)
        
        # Page size
        result = storage.get_fiscal_documents(page_size=2)
        assert hasattr(result, 'items'), "Result should have 'items' attribute"
        assert len(result.items) <= 2, "Should return at most 2 items"
        
        # Page number
        result = storage.get_fiscal_documents(page=2, page_size=2)
        assert hasattr(result, 'items'), "Result should have 'items' attribute"
        assert hasattr(result, 'total'), "Result should have 'total' attribute"
        assert result.page == 2, "Should be page 2"
        
        # Teste com page_size muito grande (deve retornar todos os itens)
        result = storage.get_fiscal_documents(page_size=1000000)
        assert hasattr(result, 'items'), "Result should be a PaginatedResponse object"
        assert len(result.items) <= 5, "Should return all items (5 or fewer)"
        
        # Teste com page_size=0 (deve usar o tamanho padrão)
        result = storage.get_fiscal_documents(page_size=0)
        assert hasattr(result, 'items'), "Result should be a PaginatedResponse object"
        assert len(result.items) > 0, "Should return items with default page size"