"""Tests for LocalJSONStorage implementation."""
import sys
import pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from backend.storage import LocalJSONStorage
import pytest
from pathlib import Path
from storage_compliance import StorageComplianceTests


@pytest.fixture
def temp_storage(tmp_path):
    """Create a temporary storage instance."""
    storage = LocalJSONStorage(data_dir=str(tmp_path))
    yield storage
    # Cleanup any files
    if (tmp_path / 'processed_documents.json').exists():
        (tmp_path / 'processed_documents.json').unlink()
    if (tmp_path / 'document_history.json').exists():
        (tmp_path / 'document_history.json').unlink()


class TestLocalJSONStorage(StorageComplianceTests):
    """Run compliance tests for LocalJSONStorage."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create a temporary storage instance."""
        storage = LocalJSONStorage(data_dir=str(tmp_path))
        yield storage
        # Cleanup
        if (tmp_path / 'processed_documents.json').exists():
            (tmp_path / 'processed_documents.json').unlink()
        if (tmp_path / 'document_history.json').exists():
            (tmp_path / 'document_history.json').unlink()

    def test_storage_path_creation(self, storage):
        """Test that storage directories are created as needed."""
        storage.save_document({'file': 'test.xml'})
        data_dir = Path(storage.data_dir)
        assert data_dir.exists()
        assert (data_dir / 'processed_documents.json').exists()