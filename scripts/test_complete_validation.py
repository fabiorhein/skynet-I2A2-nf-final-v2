#!/usr/bin/env python3
"""
Script de validação completa do sistema após a migração consolidada.
Testa se todos os componentes estão funcionando corretamente.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

def validate_database_structure():
    """Valida se todas as tabelas e colunas necessárias existem."""
    print("🗄️ Validando estrutura do banco de dados...")

    try:
        from backend.database.postgresql_storage import PostgreSQLStorage

        storage = PostgreSQLStorage()
        print("✅ PostgreSQL storage inicializado")

        # Verificar tabelas principais
        tables_query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN (
                'fiscal_documents', 'document_chunks', 'analysis_insights',
                'chat_sessions', 'chat_messages', 'document_history', 'analyses'
            )
        """
        tables = storage._execute_query(tables_query, fetch="all")
        table_names = [t['table_name'] for t in tables] if tables else []

        required_tables = [
            'fiscal_documents', 'document_chunks', 'analysis_insights',
            'chat_sessions', 'chat_messages', 'document_history', 'analyses'
        ]

        for table in required_tables:
            if table in table_names:
                print(f"   ✅ Tabela {table} existe")
            else:
                print(f"   ❌ Tabela {table} NÃO existe")
                return False

        # Verificar colunas da tabela fiscal_documents
        columns = storage._get_table_columns()
        required_columns = [
            'id', 'file_name', 'document_type', 'metadata', 'embedding_status',
            'validation_details', 'validation_metadata', 'recipient_cnpj'
        ]

        for col in required_columns:
            if col in columns:
                print(f"   ✅ Coluna {col} existe")
            else:
                print(f"   ❌ Coluna {col} NÃO existe")
                return False

        # Verificar se pgvector extension está ativo
        vector_check = storage._execute_query(
            "SELECT * FROM pg_extension WHERE extname = 'vector'",
            fetch="one"
        )

        if vector_check:
            print("   ✅ Extensão pgvector ativa")
        else:
            print("   ❌ Extensão pgvector NÃO ativa")
            return False

        return True

    except Exception as e:
        print(f"❌ Erro na validação do banco: {e}")
        return False

def test_document_persistence():
    """Testa se documentos estão sendo persistidos corretamente."""
    print("\n💾 Testando persistência de documentos...")

    try:
        from backend.database.postgresql_storage import PostgreSQLStorage

        storage = PostgreSQLStorage()

        # Salvar documento de teste
        test_doc = {
            'file_name': 'validation_test.pdf',
            'document_type': 'NFe',
            'document_number': 'VALID123',
            'issuer_cnpj': '12345678000199',
            'recipient_cnpj': '98765432000188',
            'extracted_data': {'total': '1000.00'},
            'validation_status': 'validated',
            'metadata': {'test': True},
            'embedding_status': 'pending'
        }

        saved_doc = storage.save_fiscal_document(test_doc)

        if not saved_doc or 'id' not in saved_doc:
            print("❌ Falha ao salvar documento")
            return False

        doc_id = saved_doc['id']
        print(f"✅ Documento salvo com ID: {doc_id}")

        # Verificar se documento pode ser recuperado
        retrieved_doc = storage.get_fiscal_document(doc_id)

        if not retrieved_doc:
            print("❌ Documento não encontrado após salvar")
            return False

        print("✅ Documento recuperado com sucesso")

        # Testar UPDATE de status
        update_query = """
            UPDATE fiscal_documents
            SET embedding_status = %s, last_embedding_update = %s
            WHERE id = %s
        """
        params = ('processing', '2025-10-27T16:00:00.000000', doc_id)

        result = storage._execute_query(update_query, params)

        if result == 0:
            print("❌ UPDATE falhou - nenhuma linha afetada")
            return False

        print("✅ UPDATE executado com sucesso")

        # Verificar se UPDATE foi persistido
        updated_doc = storage.get_fiscal_document(doc_id)

        if updated_doc.get('embedding_status') != 'processing':
            print("❌ UPDATE não foi persistido")
            return False

        print("✅ UPDATE persistido no banco")

        # Testar chunks
        chunks = [
            {
                'fiscal_document_id': doc_id,
                'chunk_number': 1,
                'content_text': 'Texto de teste para chunk 1',
                'metadata': {'chunk_type': 'test'}
            }
        ]

        chunk_query = """
            INSERT INTO document_chunks (fiscal_document_id, chunk_number, content_text, metadata)
            VALUES (%s, %s, %s, %s)
        """

        chunk_result = storage._execute_query(chunk_query, (
            chunks[0]['fiscal_document_id'],
            chunks[0]['chunk_number'],
            chunks[0]['content_text'],
            '{"chunk_type": "test"}'
        ))

        if chunk_result == 0:
            print("❌ Falha ao salvar chunk")
            return False

        print("✅ Chunk salvo com sucesso")

        # Verificar se chunk pode ser recuperado
        chunk_check = storage._execute_query(
            "SELECT * FROM document_chunks WHERE fiscal_document_id = %s",
            (doc_id,),
            "one"
        )

        if not chunk_check:
            print("❌ Chunk não encontrado após salvar")
            return False

        print("✅ Chunk recuperado com sucesso")

        return True

    except Exception as e:
        print(f"❌ Erro no teste de persistência: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_imports():
    """Testa se todos os módulos podem ser importados."""
    print("\n📦 Testando imports...")

    modules_to_test = [
        'streamlit',
        'backend.database.postgresql_storage',
        'backend.services.vector_store_service',
        'backend.services.document_analyzer',
        'backend.services.rag_service',
        'config'
    ]

    for module in modules_to_test:
        try:
            __import__(module)
            print(f"   ✅ {module}")
        except ImportError as e:
            print(f"   ❌ {module}: {e}")
            return False

    return True

def main():
    print("🚀 VALIDAÇÃO COMPLETA DO SISTEMA")
    print("=" * 50)

    tests = [
        ("Estrutura do Banco", validate_database_structure),
        ("Imports", test_imports),
        ("Persistência", test_document_persistence)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}:")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} passou")
            else:
                print(f"❌ {test_name} falhou")
        except Exception as e:
            print(f"❌ {test_name} falhou com erro: {e}")

    print("\n" + "=" * 50)
    print(f"📊 RESULTADO: {passed}/{total} testes passaram")

    if passed == total:
        print("🎉 TODOS OS TESTES PASSARAM!")
        print("✅ Banco de dados configurado corretamente")
        print("✅ Documentos estão sendo persistidos")
        print("✅ Chunks estão sendo salvos")
        print("✅ Sistema pronto para uso!")
        print("\n📝 Para usar a migração consolidada:")
        print("   python scripts/run_migration.py --single 100-complete_database_setup.sql")
        return True
    else:
        print(f"❌ {total - passed} testes falharam. Verificar logs.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
