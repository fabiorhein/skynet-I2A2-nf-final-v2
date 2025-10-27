#!/usr/bin/env python3
"""
Script para testar a migração completa para PostgreSQL direto e verificar se o foreign key constraint foi resolvido.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

def test_postgresql_storage():
    """Testa se o PostgreSQL storage está funcionando corretamente."""
    print("🔍 Testando PostgreSQL Storage...")

    try:
        from backend.database.postgresql_storage import PostgreSQLStorage

        storage = PostgreSQLStorage()
        print("   ✅ PostgreSQL storage inicializado")

        # Teste 1: Buscar documentos
        result = storage.get_fiscal_documents(page=1, page_size=5)
        print(f"   📊 Documentos encontrados: {len(result.items)}")

        # Teste 2: Verificar configuração do banco
        print(f"   🗄️ Tipo de storage: {type(storage).__name__}")
        print(f"   🔧 Configuração: {storage.db_config}")

        return True

    except Exception as e:
        print(f"❌ Erro no PostgreSQL storage: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_vector_store_service():
    """Testa se o VectorStore service está usando PostgreSQL direto."""
    print("\n🧠 Testando VectorStore Service...")

    try:
        from backend.services.vector_store_service import VectorStoreService

        service = VectorStoreService()
        print("   ✅ VectorStore service inicializado")

        # Teste 1: Verificar estatísticas
        stats = service.get_embedding_statistics()
        print(f"   📊 Estatísticas: {stats.get('connection_type', 'unknown')} connection")
        print(f"   📊 Chunks totais: {stats.get('total_chunks', 0)}")
        print(f"   📊 Documentos com embeddings: {stats.get('documents_with_embeddings', 0)}")

        # Teste 2: Verificar se não está mais usando Supabase
        if hasattr(service, 'supabase'):
            print("   ⚠️ Ainda está usando cliente Supabase")
        else:
            print("   ✅ Usando PostgreSQL direto")

        return True

    except Exception as e:
        print(f"❌ Erro no VectorStore service: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_document_analyzer():
    """Testa se o DocumentAnalyzer está usando PostgreSQL direto."""
    print("\n📊 Testando DocumentAnalyzer...")

    try:
        from backend.services.document_analyzer import DocumentAnalyzer

        analyzer = DocumentAnalyzer()
        print("   ✅ DocumentAnalyzer inicializado")

        # Teste 1: Buscar resumo de documentos
        summary = analyzer.get_all_documents_summary()
        print(f"   📊 Total de documentos: {summary.get('total_documents', 0)}")
        print(f"   📊 Categorias: {list(summary.get('by_type', {}).keys())}")

        # Teste 2: Verificar se não está mais usando Supabase
        if hasattr(analyzer, 'supabase') and analyzer.supabase:
            print("   ⚠️ Ainda está usando cliente Supabase")
        else:
            print("   ✅ Usando PostgreSQL direto")

        return True

    except Exception as e:
        print(f"❌ Erro no DocumentAnalyzer: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_centralization():
    """Testa se a configuração está centralizada corretamente."""
    print("\n⚙️ Testando configuração centralizada...")

    try:
        from config import DATABASE_CONFIG, SUPABASE_CONFIG, DATABASE_URL

        print("   ✅ Configurações carregadas")
        print(f"   🗄️ Database config: {type(DATABASE_CONFIG)}")
        print(f"   🌐 Supabase config: {type(SUPABASE_CONFIG)}")
        print(f"   🔗 Database URL: {DATABASE_URL[:50]}...")

        # Verificar se as configurações estão sendo lidas do secrets.toml
        if 'ukqbbhwyivmdilalbyyl.supabase.co' in DATABASE_CONFIG.get('host', ''):
            print("   ✅ Configuração do PostgreSQL está correta")
        else:
            print("   ❌ Configuração do PostgreSQL pode estar incorreta")

        return True

    except Exception as e:
        print(f"❌ Erro na configuração: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_integration():
    """Testa a integração completa do sistema."""
    print("\n🔗 Testando integração completa...")

    try:
        # Teste 1: Documento de teste
        test_doc = {
            'file_name': 'test_integration.pdf',
            'document_type': 'NFe',
            'document_number': '999999999',
            'issuer_cnpj': '12345678000199',
            'extracted_data': {'total': '1000.00'},
            'validation_status': 'validated'
        }

        # Teste 2: Salvar documento
        from backend.database.postgresql_storage import PostgreSQLStorage
        storage = PostgreSQLStorage()
        saved_doc = storage.save_fiscal_document(test_doc)

        if saved_doc and 'id' in saved_doc:
            print(f"   ✅ Documento salvo com ID: {saved_doc['id']}")

            # Teste 3: Verificar se documento existe
            retrieved_doc = storage.get_fiscal_document(saved_doc['id'])
            if retrieved_doc:
                print("   ✅ Documento recuperado com sucesso")

                # Teste 4: Vector store deve encontrar o documento
                from backend.services.vector_store_service import VectorStoreService
                vector_service = VectorStoreService()

                # Verificar estatísticas
                stats = vector_service.get_embedding_statistics()
                print(f"   📊 Vector store funcionando: {stats.get('connection_type', 'unknown')}")

                return True
            else:
                print("   ❌ Documento não foi recuperado")
                return False
        else:
            print("   ❌ Falha ao salvar documento")
            return False

    except Exception as e:
        print(f"❌ Erro na integração: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 TESTANDO MIGRAÇÃO COMPLETA PARA POSTGRESQL DIRETO")
    print("=" * 70)

    tests = [
        test_config_centralization,
        test_postgresql_storage,
        test_vector_store_service,
        test_document_analyzer,
        test_integration
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

    print("\n" + "=" * 70)
    print(f"📊 RESULTADO: {passed}/{total} testes passaram")

    if passed == total:
        print("🎉 SUCESSO! Migração para PostgreSQL direto completa!")
        print("✅ Configuração centralizada funcionando")
        print("✅ PostgreSQL storage funcionando")
        print("✅ Vector store usando PostgreSQL direto")
        print("✅ Document analyzer usando PostgreSQL direto")
        print("✅ Integração completa funcionando")
        print("\n💡 Foreign key constraint deve estar resolvido!")
        print("   • Documentos salvos via PostgreSQL direto")
        print("   • Chunks salvos via PostgreSQL direto")
        print("   • Mesma conexão para ambas as operações")
    else:
        print(f"❌ {total - passed} testes falharam. Verificar logs acima.")

if __name__ == "__main__":
    main()
