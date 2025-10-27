#!/usr/bin/env python3
"""
Teste específico para verificar o problema de persistência do documento.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

def test_document_persistence():
    """Testa se o documento está sendo realmente persistido no banco."""
    print("🔍 Testando persistência do documento...")

    try:
        from backend.database.postgresql_storage import PostgreSQLStorage

        storage = PostgreSQLStorage()
        print("✅ PostgreSQL storage inicializado")

        # Teste 1: Salvar um documento de teste
        test_doc = {
            'file_name': 'persistence_test.pdf',
            'document_type': 'NFe',
            'document_number': 'TEST123',
            'issuer_cnpj': '12345678000199',
            'extracted_data': {'total': '1000.00'},
            'validation_status': 'validated'
        }

        print("💾 Salvando documento de teste...")
        saved_doc = storage.save_fiscal_document(test_doc)

        if saved_doc and 'id' in saved_doc:
            test_id = saved_doc['id']
            print(f"✅ Documento salvo com ID: {test_id}")

            # Teste 2: Verificar se existe no banco imediatamente
            print("🔍 Verificando se documento existe no banco...")
            direct_query = "SELECT id, file_name FROM fiscal_documents WHERE id = %s"
            direct_result = storage._execute_query(direct_query, (test_id,), "one")

            if direct_result:
                print("✅ Documento encontrado no banco (query direta)")
                print(f"   ID: {direct_result['id']}")
                print(f"   File: {direct_result['file_name']}")
            else:
                print("❌ Documento NÃO encontrado no banco (query direta)")
                return False

            # Teste 3: Verificar via get_fiscal_document
            print("🔍 Verificando via get_fiscal_document...")
            retrieved_doc = storage.get_fiscal_document(test_id)

            if retrieved_doc:
                print("✅ Documento recuperado via get_fiscal_document")
                print(f"   ID: {retrieved_doc['id']}")
                print(f"   File: {retrieved_doc.get('file_name', 'N/A')}")
                return True
            else:
                print("❌ Documento NÃO encontrado via get_fiscal_document")
                return False
        else:
            print("❌ Falha ao salvar documento")
            return False

    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_update_after_save():
    """Testa se o UPDATE funciona após o documento estar persistido."""
    print("\n🧪 Testando UPDATE após documento estar persistido...")

    try:
        from backend.database.postgresql_storage import PostgreSQLStorage

        storage = PostgreSQLStorage()

        # Primeiro, salvar um documento
        test_doc = {
            'file_name': 'update_test.pdf',
            'document_type': 'NFe',
            'document_number': 'UPDATE123',
            'issuer_cnpj': '98765432000188',
            'extracted_data': {'total': '2000.00'},
            'validation_status': 'validated'
        }

        saved_doc = storage.save_fiscal_document(test_doc)
        test_id = saved_doc['id']

        # Verificar se documento existe
        if not storage.get_fiscal_document(test_id):
            print("❌ Documento não encontrado após salvar")
            return False

        print(f"✅ Documento {test_id} confirmado no banco")

        # Agora testar UPDATE de status
        print("🔄 Testando UPDATE de embedding_status...")
        update_query = """
            UPDATE fiscal_documents
            SET embedding_status = %s, last_embedding_update = %s
            WHERE id = %s
        """
        params = ('processing', '2025-10-27T15:50:00.000000', test_id)

        result = storage._execute_query(update_query, params)
        print(f"📊 UPDATE resultou em {result} linhas afetadas")

        if result > 0:
            print("✅ UPDATE executado com sucesso")

            # Verificar se o UPDATE foi persistido
            updated_doc = storage.get_fiscal_document(test_id)
            if updated_doc and updated_doc.get('embedding_status') == 'processing':
                print("✅ UPDATE persistido no banco")
                return True
            else:
                print("❌ UPDATE não foi persistido")
                return False
        else:
            print("❌ UPDATE falhou - nenhuma linha afetada")
            return False

    except Exception as e:
        print(f"❌ Erro no teste UPDATE: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 TESTE DE PERSISTÊNCIA DO DOCUMENTO")
    print("=" * 50)

    test1_ok = test_document_persistence()
    test2_ok = test_update_after_save()

    print("\n" + "=" * 50)
    print("📊 RESULTADOS:")
    print(f"   Persistência: {'✅' if test1_ok else '❌'}")
    print(f"   UPDATE: {'✅' if test2_ok else '❌'}")

    if test1_ok and test2_ok:
        print("🎉 TODOS OS TESTES PASSARAM!")
        print("✅ Documento está sendo persistido corretamente")
        print("✅ UPDATE funciona após documento estar salvo")
        return True
    else:
        print("❌ Alguns testes falharam!")
        return False

if __name__ == "__main__":
    main()
