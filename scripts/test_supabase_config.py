#!/usr/bin/env python3
"""
Script para testar as configurações do Supabase e validar o sistema completo.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

def test_supabase_config():
    """Testa se as configurações do Supabase estão sendo carregadas corretamente."""
    print("🔧 Testando configurações do Supabase...")

    try:
        from config import (
            DATABASE_CONFIG, DATABASE_URL, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD,
            DB_SSL_MODE, DB_CONNECT_TIMEOUT, DB_POOL_MODE
        )

        print("✅ Configurações carregadas com sucesso:")
        print(f"   Host: {DB_HOST}")
        print(f"   Port: {DB_PORT}")
        print(f"   User: {DB_USER}")
        print(f"   Database: {DATABASE_CONFIG['dbname']}")
        print(f"   SSL Mode: {DB_SSL_MODE}")
        print(f"   Connect Timeout: {DB_CONNECT_TIMEOUT}")
        print(f"   Pool Mode: {DB_POOL_MODE}")
        print(f"   Connection String: {DATABASE_URL}")

        # Testar conexão com o banco
        print("\n🗄️ Testando conexão PostgreSQL...")
        import psycopg2

        conn = psycopg2.connect(**DATABASE_CONFIG)
        print("   ✅ Conexão estabelecida com sucesso")

        # Verificar se as tabelas existem
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('fiscal_documents', 'document_chunks', 'analysis_insights')
            """)
            tables = cursor.fetchall()
            table_names = [t[0] for t in tables]

            print(f"   📊 Tabelas encontradas: {table_names}")

            if 'fiscal_documents' in table_names:
                print("   ✅ Tabela fiscal_documents existe")
            else:
                print("   ❌ Tabela fiscal_documents NÃO existe")

        conn.close()
        print("   ✅ Conexão fechada")

        return True

    except Exception as e:
        print(f"❌ Erro na configuração/conexão: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_document_operations():
    """Testa operações básicas de documento."""
    print("\n📄 Testando operações de documento...")

    try:
        from backend.database.postgresql_storage import PostgreSQLStorage

        storage = PostgreSQLStorage()
        print("   ✅ PostgreSQL storage inicializado")

        # Testar salvamento de documento
        test_doc = {
            'file_name': 'supabase_test.pdf',
            'document_type': 'NFe',
            'document_number': 'SUPABASE123',
            'issuer_cnpj': '12345678000199',
            'recipient_cnpj': '98765432000188',
            'extracted_data': {'total': '1000.00'},
            'validation_status': 'validated',
            'metadata': {'test': True},
            'embedding_status': 'pending'
        }

        print("   💾 Salvando documento de teste...")
        saved_doc = storage.save_fiscal_document(test_doc)

        if saved_doc and 'id' in saved_doc:
            doc_id = saved_doc['id']
            print(f"   ✅ Documento salvo com ID: {doc_id}")

            # Testar recuperação
            retrieved_doc = storage.get_fiscal_document(doc_id)

            if retrieved_doc:
                print("   ✅ Documento recuperado com sucesso")
                print(f"      File: {retrieved_doc.get('file_name', 'N/A')}")
                print(f"      Status: {retrieved_doc.get('validation_status', 'N/A')}")
            else:
                print("   ❌ Documento não encontrado após salvar")
                return False

            # Testar UPDATE de status
            update_query = """
                UPDATE fiscal_documents
                SET embedding_status = %s, last_embedding_update = %s
                WHERE id = %s
            """
            params = ('processing', '2025-10-27T16:30:00.000000', doc_id)

            result = storage._execute_query(update_query, params)

            if result > 0:
                print("   ✅ UPDATE de status executado com sucesso")

                # Verificar se UPDATE foi persistido
                updated_doc = storage.get_fiscal_document(doc_id)
                if updated_doc.get('embedding_status') == 'processing':
                    print("   ✅ UPDATE persistido no banco")
                else:
                    print("   ❌ UPDATE não foi persistido")
                    return False
            else:
                print("   ❌ UPDATE falhou")
                return False

            return True
        else:
            print("   ❌ Falha ao salvar documento")
            return False

    except Exception as e:
        print(f"❌ Erro nas operações de documento: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 TESTE COMPLETO DAS CONFIGURAÇÕES DO SUPABASE")
    print("=" * 60)

    tests = [
        ("Configurações Supabase", test_supabase_config),
        ("Operações de Documento", test_document_operations)
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

    print("\n" + "=" * 60)
    print(f"📊 RESULTADO: {passed}/{total} testes passaram")

    if passed == total:
        print("🎉 TODOS OS TESTES PASSARAM!")
        print("✅ Configurações do Supabase funcionando")
        print("✅ PostgreSQL conectado e operacional")
        print("✅ Sistema pronto para uso!")
        print("\n📝 Para usar:")
        print("   1. streamlit run app.py")
        print("   2. python scripts/test_complete_validation.py")
        return True
    else:
        print(f"❌ {total - passed} testes falharam. Verificar logs.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
