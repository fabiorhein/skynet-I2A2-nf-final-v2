import asyncio
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_embedding_service():
    service = MagicMock()
    service.process_document_for_embedding.return_value = [
        {
            "content_text": "Nota fiscal emitida por empresa de tecnologia",
            "embedding": [0.2] * 768,
            "metadata": {
                "document_id": "doc-xyz",
                "chunk_number": 0,
                "total_chunks": 1,
            },
        }
    ]
    service.generate_query_embedding.return_value = [0.1] * 768
    return service


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.update_document_embedding_status.return_value = True
    store.save_document_chunks.return_value = ["chunk-1"]
    store.get_embedding_statistics.return_value = {
        "documents_with_embeddings": 1,
        "total_chunks": 1,
    }
    store.search_similar_chunks.return_value = [
        {
            "content_text": "Produto x vendido",
            "metadata": {"chunk_number": 0},
            "fiscal_document_id": "doc-xyz",
            "similarity_score": 0.8,
        }
    ]
    store.get_document_context.return_value = [
        {
            "fiscal_document_id": "doc-xyz",
            "chunks_content": "Produto x vendido",
            "total_similarity": 0.9,
            "document_type": "NFe",
            "issuer_cnpj": "12345678000199",
        }
    ]
    return store


@pytest.fixture
def rag_service(mock_embedding_service, mock_vector_store, monkeypatch):
    monkeypatch.setattr(
        "backend.services.fallback_embedding_service.FallbackEmbeddingService",
        MagicMock(return_value=mock_embedding_service),
    )
    monkeypatch.setattr(
        "backend.services.rag_service.VectorStoreService",
        MagicMock(return_value=mock_vector_store),
    )

    from backend.services.rag_service import RAGService

    return RAGService()


@pytest.mark.asyncio
async def test_process_document_for_rag_success(rag_service, mock_embedding_service, mock_vector_store):
    document = {"id": "doc-xyz", "file_name": "nota.pdf"}

    result = await rag_service.process_document_for_rag(document)

    assert result["success"] is True
    assert result["chunks_processed"] == 1
    mock_embedding_service.process_document_for_embedding.assert_called_once()
    mock_vector_store.save_document_chunks.assert_called_once()
    mock_vector_store.update_document_embedding_status.assert_any_call("doc-xyz", "completed")


@pytest.mark.asyncio
async def test_process_document_for_rag_error(rag_service, mock_embedding_service, mock_vector_store):
    mock_embedding_service.process_document_for_embedding.side_effect = RuntimeError("embedding failed")

    result = await rag_service.process_document_for_rag({"id": "doc-xyz"})

    assert result["success"] is False
    assert result["error"] == "embedding failed"
    mock_vector_store.update_document_embedding_status.assert_any_call("doc-xyz", "failed")


@pytest.mark.asyncio
async def test_answer_query_success(rag_service, mock_embedding_service, mock_vector_store, monkeypatch):
    async def fake_generate_with_context(query, context, temperature=0.1):
        return "Resposta contextualizada"

    monkeypatch.setattr(
        rag_service,
        "_generate_response_with_context",
        fake_generate_with_context,
    )

    response = await rag_service.answer_query("Quais documentos foram emitidos?", filters=None)

    assert response["status"] == "success"
    assert response["answer"] == "Resposta contextualizada"
    assert len(response["context_docs"]) == 1
    assert mock_vector_store.search_similar_chunks.called


@pytest.mark.asyncio
async def test_answer_query_no_chunks(rag_service, mock_vector_store):
    mock_vector_store.search_similar_chunks.return_value = []
    mock_vector_store.get_embedding_statistics.return_value = {"documents_with_embeddings": 0}

    response = await rag_service.answer_query("Alguma nota fiscal?", filters=None)

    assert response["status"] == "no_documents"
    assert "Nenhum documento foi processado" in response["answer"]


@pytest.mark.asyncio
async def test_answer_query_no_matches(rag_service, mock_vector_store):
    mock_vector_store.search_similar_chunks.return_value = []
    mock_vector_store.get_embedding_statistics.return_value = {"documents_with_embeddings": 2}

    response = await rag_service.answer_query("Notas fiscais com problema", filters=None)

    assert response["status"] == "no_matches"
    assert "Tente reformular a pergunta" in response["answer"]
