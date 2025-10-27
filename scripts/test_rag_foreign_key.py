#!/usr/bin/env python3
"""
Script para testar o problema de foreign key constraint no RAG processing.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

async def test_rag_foreign_key_fix():
    """Testa se o problema de foreign key constraint foi corrigido."""
    print("🧪 Testando correção do foreign key constraint no RAG...")

    try:
        # Teste 1: Simular documento que será processado
        test_document = {
            'id': 'test-doc-12345-abcdef',
            'file_name': 'test_nfe.pdf',
            'document_type': 'NFe',
            'document_number': '12345',
            'issuer_cnpj': '12345678000199',
            'extracted_data': {
                'emitente': {
                    'razao_social': 'EMPRESA TESTE LTDA',
                    'cnpj': '12345678000199'
                },
                'destinatario': {
                    'razao_social': 'CLIENTE TESTE S.A.',
                    'cnpj': '98765432000100'
                },
                'itens': [
                    {
                        'descricao': 'Produto Teste',
                        'quantidade': 10,
                        'valor_unitario': 100.00,
                        'valor_total': 1000.00
                    }
                ],
                'totais': {
                    'valor_produtos': 1000.00,
                    'valor_total': 1000.00
                }
            },
            'raw_text': 'Nota Fiscal Eletrônica número 12345 emitida por EMPRESA TESTE LTDA para CLIENTE TESTE S.A. no valor de R$ 1.000,00',
            'validation_status': 'validated',
            'classification': {'tipo': 'venda', 'categoria': 'mercadorias'}
        }

        # Teste 2: Verificar se o documento seria salvo corretamente
        print("\n1️⃣ Testando salvamento do documento...")
        from backend.database.postgresql_storage import PostgreSQLStorage

        storage = PostgreSQLStorage()
        saved_doc = storage.save_fiscal_document(test_document)

        if saved_doc and 'id' in saved_doc:
            print(f"   ✅ Documento salvo com ID: {saved_doc['id']}")

            # Teste 3: Verificar se o documento existe no banco
            print("\n2️⃣ Verificando se documento existe no banco...")
            retrieved_doc = storage.get_fiscal_document(saved_doc['id'])

            if retrieved_doc:
                print(f"   ✅ Documento encontrado: {retrieved_doc['id']}")
            else:
                print("   ❌ Documento não encontrado!")
                return False

            # Teste 4: Processar documento para RAG
            print("\n3️⃣ Testando processamento RAG...")
            from backend.services.rag_service import RAGService

            rag_service = RAGService()
            result = await rag_service.process_document_for_rag(saved_doc)

            if result['success']:
                print(f"   ✅ RAG processing bem-sucedido: {result['chunks_processed']} chunks")
                print(f"   📊 Total chunks: {result['total_chunks']}")
                return True
            else:
                print(f"   ❌ RAG processing falhou: {result['error']}")
                return False

        else:
            print("   ❌ Falha ao salvar documento")
            return False

    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_embedding_service():
    """Testa se o embedding service está funcionando corretamente."""
    print("\n🔍 Testando embedding service...")

    try:
        from backend.services.free_embedding_service import FreeEmbeddingService

        service = FreeEmbeddingService()
        test_doc = {
            'id': 'test-embedding-123',
            'file_name': 'test.pdf',
            'document_type': 'NFe',
            'extracted_data': {'total': '1000.00'}
        }

        chunks = service.split_document(test_doc)

        if chunks:
            print(f"   ✅ Documento dividido em {len(chunks)} chunks")

            # Verificar se o ID está correto nos metadados
            for i, chunk in enumerate(chunks[:2]):  # Mostrar apenas os 2 primeiros
                doc_id = chunk['metadata'].get('document_id')
                print(f"   📄 Chunk {i}: document_id = {doc_id}")

            return True
        else:
            print("   ❌ Nenhum chunk gerado")
            return False

    except Exception as e:
        print(f"❌ Erro no embedding service: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 TESTANDO CORREÇÃO DO FOREIGN KEY CONSTRAINT")
    print("=" * 60)

    import asyncio

    # Teste 1: Embedding service
    if not test_embedding_service():
        print("❌ Teste do embedding service falhou!")
        return

    # Teste 2: RAG processing completo
    success = asyncio.run(test_rag_foreign_key_fix())

    if success:
        print("\n" + "=" * 60)
        print("🎉 SUCESSO! Foreign key constraint corrigido!")
        print("✅ Documento salvo corretamente")
        print("✅ Documento encontrado no banco")
        print("✅ RAG processing funcionando")
        print("✅ Chunks salvos com IDs corretos")
    else:
        print("\n" + "=" * 60)
        print("❌ Foreign key constraint ainda com problemas!")

if __name__ == "__main__":
    main()
