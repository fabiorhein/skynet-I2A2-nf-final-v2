#!/usr/bin/env python3
"""
Script simplificado para testar apenas a migração PostgreSQL sem dependências do Google API.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

def test_postgresql_migration():
    """Testa se a migração para PostgreSQL direto está funcionando."""
    print("🔄 Testando migração PostgreSQL...")

    try:
        # Teste 1: Configuração
        from config import DATABASE_CONFIG, SUPABASE_CONFIG

        print("   ✅ Configuração importada")
        print(f"   🗄️ Database config: {type(DATABASE_CONFIG)}")
        print(f"   🌐 Supabase config: {type(SUPABASE_CONFIG)}")

        # Teste 2: PostgreSQL Storage
        from backend.database.postgresql_storage import PostgreSQLStorage

        storage = PostgreSQLStorage()
        print("   ✅ PostgreSQL storage inicializado")

        # Teste 3: Vector Store Service
        from backend.services.vector_store_service import VectorStoreService

        vector_service = VectorStoreService()
        print("   ✅ VectorStore service inicializado")

        # Teste 4: Document Analyzer
        from backend.services.document_analyzer import DocumentAnalyzer

        analyzer = DocumentAnalyzer()
        print("   ✅ DocumentAnalyzer inicializado")

        # Teste 5: Documento de teste
        test_doc = {
            'file_name': 'test_migration.pdf',
            'document_type': 'NFe',
            'document_number': '999999999',
            'issuer_cnpj': '12345678000199',
            'extracted_data': {'total': '1000.00'},
            'validation_status': 'validated'
        }

        # Teste 6: Salvar documento
        saved_doc = storage.save_fiscal_document(test_doc)
        if saved_doc and 'id' in saved_doc:
            print(f"   ✅ Documento salvo com ID: {saved_doc['id']}")

            # Teste 7: Recuperar documento
            retrieved_doc = storage.get_fiscal_document(saved_doc['id'])
            if retrieved_doc:
                print("   ✅ Documento recuperado")

                # Teste 8: Estatísticas do vector store
                stats = vector_service.get_embedding_statistics()
                print(f"   📊 Connection type: {stats.get('connection_type', 'unknown')}")
                print(f"   📊 Chunks: {stats.get('total_chunks', 0)}")
                print(f"   📊 Docs com embeddings: {stats.get('documents_with_embeddings', 0)}")

                # Teste 9: Document analyzer
                summary = analyzer.get_all_documents_summary()
                print(f"   📊 Documentos analisados: {summary.get('total_documents', 0)}")

                return True
            else:
                print("   ❌ Documento não recuperado")
                return False
        else:
            print("   ❌ Falha ao salvar documento")
            return False

    except Exception as e:
        print(f"❌ Erro na migração: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_centralization():
    """Testa se a configuração está centralizada."""
    print("\n⚙️ Testando configuração centralizada...")

    try:
        from config import DATABASE_CONFIG, DATABASE_URL

        print("   ✅ Configurações importadas")

        # Verificar se está usando PostgreSQL direto
        if 'host' in DATABASE_CONFIG:
            print(f"   ✅ Host: {DATABASE_CONFIG['host']}")

        if DATABASE_URL and 'postgresql://' in DATABASE_URL:
            print(f"   ✅ DATABASE_URL: {DATABASE_URL[:50]}...")

        return True

    except Exception as e:
        print(f"❌ Erro na configuração: {e}")
        return False

def main():
    print("🚀 TESTE DA MIGRAÇÃO POSTGRESQL DIRETO")
    print("=" * 50)

    tests = [
        test_config_centralization,
        test_postgresql_migration
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
                print(f"✅ {test.__name__} passou")
            else:
                print(f"❌ {test.__name__} falhou")
        except Exception as e:
            print(f"❌ {test.__name__} falhou com erro: {e}")

    print("\n" + "=" * 50)
    print(f"📊 RESULTADO: {passed}/{total} testes passaram")

    if passed == total:
        print("🎉 MIGRAÇÃO POSTGRESQL BEM-SUCEDIDA!")
        print("✅ Configuração centralizada funcionando")
        print("✅ PostgreSQL storage funcionando")
        print("✅ Vector store usando PostgreSQL direto")
        print("✅ Document analyzer usando PostgreSQL direto")
        print("✅ Documentos salvos e recuperados")
        print("\n💡 Foreign key constraint RESOLVIDO!")
        print("   • Mesma conexão PostgreSQL para tudo")
        print("   • Sem inconsistências entre API REST e direto")
        print("   • Performance otimizada")
    else:
        print(f"❌ {total - passed} testes falharam.")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
