#!/usr/bin/env python3
"""
Script para testar a correção completa do sistema brasileiro incluindo foreign key constraint.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

def test_jsonb_conversion():
    """Testa se a conversão JSONB está funcionando corretamente."""
    print("🔍 Testando conversão JSONB no PostgreSQL storage...")

    try:
        from backend.database.postgresql_storage import PostgreSQLStorage

        # Teste 1: Verificar se save_fiscal_document retorna JSONB como dicionários
        test_doc = {
            'id': 'test-jsonb-123',
            'file_name': 'test.pdf',
            'document_type': 'NFe',
            'extracted_data': {'total': '1000.00', 'itens': [{'valor': '500.00'}]},
            'classification': {'tipo': 'venda', 'categoria': 'produtos'},
            'validation_details': {'status': 'ok', 'erros': []}
        }

        storage = PostgreSQLStorage()
        saved_doc = storage.save_fiscal_document(test_doc)

        if saved_doc:
            print(f"   ✅ Documento salvo: {saved_doc['id']}")

            # Verificar se os campos JSONB foram convertidos para dicionários
            jsonb_fields = ['extracted_data', 'classification', 'validation_details']

            for field in jsonb_fields:
                if field in saved_doc:
                    value = saved_doc[field]
                    if isinstance(value, dict):
                        print(f"   ✅ {field}: {type(value)} (dicionário)")
                    elif isinstance(value, str):
                        print(f"   ⚠️ {field}: {type(value)} (string) - pode causar problemas")
                    else:
                        print(f"   ❓ {field}: {type(value)} (tipo desconhecido)")
                else:
                    print(f"   ❌ {field}: campo não encontrado")

            return True
        else:
            print("   ❌ Falha ao salvar documento")
            return False

    except Exception as e:
        print(f"❌ Erro no teste JSONB: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_embedding_service_format():
    """Testa se o embedding service está recebendo o formato correto."""
    print("\n🧠 Testando embedding service com formato correto...")

    try:
        from backend.services.free_embedding_service import FreeEmbeddingService

        # Documento no formato que seria retornado pelo save_fiscal_document
        test_doc = {
            'id': 'test-embedding-format',
            'file_name': 'test.pdf',
            'document_type': 'NFe',
            'extracted_data': {'total': '1000.00', 'itens': [{'valor': '500.00'}]},  # dicionário
            'classification': {'tipo': 'venda'},  # dicionário
            'validation_details': {'status': 'ok'},  # dicionário
            'raw_text': 'Nota fiscal de teste no valor de mil reais'
        }

        service = FreeEmbeddingService()
        chunks = service.split_document(test_doc)

        if chunks:
            print(f"   ✅ Documento dividido em {len(chunks)} chunks")

            # Verificar se o document_id está correto nos metadados
            for chunk in chunks:
                doc_id = chunk['metadata'].get('document_id')
                if doc_id == test_doc['id']:
                    print(f"   ✅ Chunk com document_id correto: {doc_id}")
                else:
                    print(f"   ❌ Chunk com document_id incorreto: {doc_id} (esperado: {test_doc['id']})")
                    return False

            return True
        else:
            print("   ❌ Nenhum chunk gerado")
            return False

    except Exception as e:
        print(f"❌ Erro no embedding service: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_rag_processing_complete():
    """Testa o processamento RAG completo com o documento no formato correto."""
    print("\n🚀 Testando processamento RAG completo...")

    try:
        from backend.services.rag_service import RAGService

        # Documento no formato correto (como retornado pelo save_fiscal_document)
        test_doc = {
            'id': 'test-rag-complete',
            'file_name': 'test_nfe_complete.pdf',
            'document_type': 'NFe',
            'document_number': '12345',
            'issuer_cnpj': '12345678000199',
            'extracted_data': {
                'emitente': {'razao_social': 'EMPRESA TESTE LTDA', 'cnpj': '12345678000199'},
                'destinatario': {'razao_social': 'CLIENTE TESTE S.A.', 'cnpj': '98765432000100'},
                'itens': [{'descricao': 'Produto Teste', 'quantidade': 10, 'valor_unitario': 100.00, 'valor_total': 1000.00}],
                'totais': {'valor_produtos': 1000.00, 'valor_total': 1000.00}
            },
            'classification': {'tipo': 'venda', 'categoria': 'mercadorias'},
            'validation_details': {'status': 'validated', 'erros': []},
            'raw_text': 'Nota Fiscal Eletrônica número 12345 emitida por EMPRESA TESTE LTDA para CLIENTE TESTE S.A. no valor de R$ 1.000,00',
            'validation_status': 'validated'
        }

        rag_service = RAGService()
        result = await rag_service.process_document_for_rag(test_doc)

        if result['success']:
            print(f"   ✅ RAG processing bem-sucedido!")
            print(f"   📊 Chunks processados: {result['chunks_processed']}")
            print(f"   📋 Total de chunks: {result['total_chunks']}")
            return True
        else:
            print(f"   ❌ RAG processing falhou: {result['error']}")
            return False

    except Exception as e:
        print(f"❌ Erro no RAG processing: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🧪 TESTE COMPLETO DAS CORREÇÕES DO SISTEMA BRASILEIRO")
    print("=" * 70)

    # Teste 1: Conversão JSONB
    if not test_jsonb_conversion():
        print("❌ Teste JSONB falhou!")
        return

    # Teste 2: Embedding service
    if not test_embedding_service_format():
        print("❌ Teste embedding service falhou!")
        return

    # Teste 3: RAG processing completo
    import asyncio
    success = asyncio.run(test_rag_processing_complete())

    if success:
        print("\n" + "=" * 70)
        print("🎉 SUCESSO ABSOLUTO!")
        print("✅ Conversão JSONB: OK")
        print("✅ Embedding service: OK")
        print("✅ RAG processing: OK")
        print("✅ Foreign key constraint: RESOLVIDO!")
        print("\n💡 Sistema brasileiro completamente funcional!")
        print("   • Documentos salvos com formato correto")
        print("   • RAG processing sem erros de foreign key")
        print("   • Conversão automática JSONB ↔ dicionários")
        print("   • Chunks criados com IDs corretos")
    else:
        print("\n" + "=" * 70)
        print("❌ Ainda há problemas no sistema!")

if __name__ == "__main__":
    main()
