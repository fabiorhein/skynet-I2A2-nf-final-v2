#!/usr/bin/env python3
"""
Simple test script to verify PostgreSQL document saving is working correctly.
"""
import sys
import os
sys.path.append('.')

from backend.database.postgresql_storage import PostgreSQLStorage

def test_simple_document_saving():
    """Test basic document saving without update operations."""
    print("=== Testing Simple PostgreSQL Document Saving ===\n")

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
            print(f"   Type: {retrieved_doc['document_type']}")
            print(f"   Value: R$ {retrieved_doc['total_value']}")
        else:
            print("❌ Document not found after saving!")
            return False

        # Test getting all documents
        print("\n5. Testing document listing...")
        all_docs = storage.get_fiscal_documents(page=1, page_size=10)
        print(f"✅ Total documents in database: {all_docs.total}")

        for doc in all_docs.items:
            print(f"   - {doc['file_name']} ({doc['document_type']}) - ID: {doc['id'][:8]}...")

        print("\n=== Simple test completed successfully! ===")
        return True

    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_simple_document_saving()
    sys.exit(0 if success else 1)
