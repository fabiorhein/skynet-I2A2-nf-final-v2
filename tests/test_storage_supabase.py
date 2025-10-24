"""Tests for SupabaseStorage implementation."""
import sys
import pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from backend.storage import SupabaseStorage, StorageError
import pytest
import os
import uuid
from storage_compliance import StorageComplianceTests


@pytest.fixture
def supabase_storage():
    """Create a Supabase storage instance for testing.
    
    Requires environment variables:
    - TEST_SUPABASE_URL: Test project URL
    - TEST_SUPABASE_KEY: Test project API key
    """
    url = os.getenv('TEST_SUPABASE_URL')
    key = os.getenv('TEST_SUPABASE_KEY')
    
    if not url or not key:
        pytest.skip("TEST_SUPABASE_URL and TEST_SUPABASE_KEY required for Supabase tests")
    
    storage = SupabaseStorage(url=url, key=key)
    yield storage


class TestSupabaseStorage(StorageComplianceTests):
    """Run compliance tests for SupabaseStorage."""

    @pytest.fixture
    def storage(self):
        """Create a Supabase storage instance for testing."""
        url = os.getenv('TEST_SUPABASE_URL')
        key = os.getenv('TEST_SUPABASE_KEY')
        
        if not url or not key:
            pytest.skip("TEST_SUPABASE_URL and TEST_SUPABASE_KEY required for Supabase tests")
        
        return SupabaseStorage(url=url, key=key)

    @pytest.mark.integration
    def test_supabase_specific_errors(self, storage):
        """Test Supabase-specific error handling."""
        # Test saving invalid history event (missing required fields)
        with pytest.raises(StorageError):
            storage.save_history({})  # Missing fiscal_document_id
        
        # Test invalid document ID
        history = storage.get_document_history('invalid-id')
        assert len(history) == 0  # Should return empty list
    
    @pytest.mark.integration
    def test_rest_api_integration(self, storage):
        """Test that REST API calls work properly."""
        # Create a unique test document
        test_number = str(uuid.uuid4())
        doc = {
            'file_name': 'test.xml',
            'document_type': 'NFe',
            'document_number': test_number,
            'issuer_cnpj': '12345678000195'
        }
        
        # Test POST request
        saved = storage.save_document(doc)
        assert 'id' in saved
        assert saved.get('document_number') == test_number
        
        # Test GET request with filters
        result = storage.get_fiscal_documents(
            filters={'document_number': test_number}
        )
        assert result['total'] == 1
        assert result['items'][0]['document_number'] == test_number