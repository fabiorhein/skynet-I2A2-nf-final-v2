import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_sentence_transformer(monkeypatch):
    mock_model = MagicMock()
    mock_model.encode.side_effect = [
        [0.1, 0.1, 0.2],
        [0.3, 0.4, 0.5],
    ]

    monkeypatch.setattr(
        "backend.services.free_embedding_service.SentenceTransformer",
        MagicMock(return_value=mock_model),
    )
    monkeypatch.setattr(
        "backend.services.free_embedding_service.SENTENCE_TRANSFORMERS_AVAILABLE",
        True,
    )
    return mock_model


def test_generate_embeddings_and_query_embeddings(mock_sentence_transformer):
    from backend.services.free_embedding_service import FreeEmbeddingService

    service = FreeEmbeddingService(model_name="all-mpnet-base-v2")

    embedding = service.generate_embedding("Nota fiscal com valor de R$ 500,00")
    query_embedding = service.generate_query_embedding("Buscar notas fiscais do mês")

    assert embedding == [0.1, 0.1, 0.2]
    assert query_embedding == [0.3, 0.4, 0.5]
    assert service.embedding_dimension == 768
    mock_sentence_transformer.encode


def test_generate_embedding_invalid_input(mock_sentence_transformer):
    from backend.services.free_embedding_service import FreeEmbeddingService

    service = FreeEmbeddingService(model_name="all-MiniLM-L6-v2")

    with pytest.raises(ValueError):
        service.generate_embedding("")


def test_import_error_when_sentence_transformer_missing(monkeypatch):
    monkeypatch.setattr(
        "backend.services.free_embedding_service.SENTENCE_TRANSFORMERS_AVAILABLE",
        False,
    )

    with pytest.raises(ImportError):
        from backend.services.free_embedding_service import FreeEmbeddingService

        FreeEmbeddingService()
