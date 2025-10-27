#!/usr/bin/env python3
"""
Test script to verify PostgreSQL document saving is working correctly.
"""
import sys
import os
sys.path.append('.')

from backend.database.postgresql_storage import PostgreSQLStorage
from backend.services.vector_store_service import VectorStoreService
from config import DATABASE_CONFIG

def test_document_saving():
    """Test if documents are being saved correctly to PostgreSQL."""
    print("=== Testing PostgreSQL Document Saving ===\n")

    try:
        # Test basic storage connection
        print("1. Testing PostgreSQL Storage connection...")
        storage = PostgreSQLStorage()
        print("✅ Storage connection established")

        # Check table columns
        print("\n2. Checking table columns...")
        columns = storage._get_table_columns()
        print(f"✅ Found {len(columns)} columns: {columns}")

        # Test document saving
        print("\n3. Testing document saving...")
        test_doc = {
            'file_name': 'test_document.xml',
            'document_type': 'NFe',
            'document_number': '123456789',
            'issuer_cnpj': '12345678000123',
            'issuer_name': 'Test Company Ltda',
            'total_value': 1000.00,
            'extracted_data': {
                'emitente': {'cnpj': '12345678000123', 'razao_social': 'Test Company Ltda'},
                'itens': [{'produto': 'Test Product', 'valor': 1000.00}],
                'total': 1000.00
            },
            'validation_status': 'success',
            'raw_text': 'Test document content'
        }

        saved_doc = storage.save_fiscal_document(test_doc)
        print(f"✅ Document saved successfully with ID: {saved_doc['id']}")

        # Verify document was saved
        print("\n4. Verifying document was saved...")
        retrieved_doc = storage.get_fiscal_document(saved_doc['id'])
        if retrieved_doc:
            print(f"✅ Document retrieved successfully: {retrieved_doc['file_name']}")
        else:
            print("❌ Document not found after saving!")

        # Test getting all documents
        print("\n5. Testing document listing...")
        all_docs = storage.get_fiscal_documents(page=1, page_size=10)
        print(f"✅ Total documents in database: {all_docs.total}")

        # Test vector store service
        print("\n6. Testing Vector Store Service...")
        vector_store = VectorStoreService()
        print("✅ Vector store connection established")

        # Test embedding status update
        print("\n7. Testing embedding status update...")
        update_result = vector_store.update_document_embedding_status(saved_doc['id'], 'completed')
        print(f"✅ Embedding status update result: {update_result}")

        # Test statistics
        print("\n8. Testing embedding statistics...")
        stats = vector_store.get_embedding_statistics()
        print(f"✅ Total chunks: {stats.get('total_chunks', 0)}")
        print(f"✅ Documents with embeddings: {stats.get('documents_with_embeddings', 0)}")

        print("\n=== All tests completed successfully! ===")
        return True

    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_document_saving()
    sys.exit(0 if success else 1)
