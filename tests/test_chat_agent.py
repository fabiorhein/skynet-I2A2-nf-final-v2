import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.chat_agent import ChatAgent, ChatResponse


@pytest.fixture
def chat_agent(monkeypatch):
    storage = MagicMock()

    # Always assume Gemini is available to exercise cache logic
    monkeypatch.setattr("backend.agents.chat_agent.GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("backend.agents.chat_agent.ChatGoogleGenerativeAI", MagicMock(return_value=MagicMock(name="gemini")))

    # Stub DocumentAnalyzer to avoid hitting real storage
    fake_analyzer = AsyncMock()
    fake_analyzer.get_all_documents_summary.return_value = {"total_documents": 0}
    monkeypatch.setattr("backend.agents.chat_agent.DocumentAnalyzer", MagicMock(return_value=fake_analyzer))

    agent = ChatAgent(storage)
    agent.document_analyzer = fake_analyzer

    return agent, storage


@pytest.fixture
async def session(chat_agent):
    agent, storage = chat_agent
    storage.create_chat_session.return_value = {"id": "session-1"}
    return agent, storage, await agent.create_session("teste")


def test_generate_response_same_session_cache(monkeypatch, chat_agent):
    agent, storage = chat_agent

    # Configure cache to return hit for same session
    cached_payload = {
        "content": "Resposta anterior",
        "metadata": {"model": "gemini"},
        "cached": True,
        "cached_session_id": "session-abc",
        "cached_at": "2025-01-01T12:00:00Z",
    }
    agent.cache.get_cached_response = AsyncMock(return_value=cached_payload)
    agent.save_message = AsyncMock()

    response: ChatResponse = asyncio.run(
        agent.generate_response("session-abc", "Qual a análise?", context={"query_type": "analysis"})
    )

    agent.cache.get_cached_response.assert_awaited_once()
    agent.save_message.assert_awaited_once()
    assert response.cached is True
    assert "Pergunta repetida" in response.content
    assert response.metadata["reused_in_session"] is True
    assert response.metadata["tokens_used"] == 0


def test_generate_response_cache_other_session(monkeypatch, chat_agent):
    agent, storage = chat_agent

    # Cache hit belongs to another session – should ignore and continue pipeline

    cached_payload = {
        "content": "Resposta prévia",
        "metadata": {"model": "gemini"},
        "cached": True,
        "cached_session_id": "session-xyz",
        "cached_at": "2025-01-01T12:00:00Z",
    }
    agent.cache.get_cached_response = AsyncMock(return_value=cached_payload)

    # Avoid hitting Gemini for the test
    agent._handle_specific_search = AsyncMock(return_value=ChatResponse("Resposta nova", {"tokens_used": 10}))

    response = asyncio.run(
        agent.generate_response("session-abc", "Preciso da análise", context={"query_type": "analysis"})
    )

    agent.cache.get_cached_response.assert_awaited_once()
    agent._handle_specific_search.assert_awaited_once()
    assert response.cached is False
    assert response.content == "Resposta nova"


def test_generate_response_no_cache(monkeypatch, chat_agent):
    agent, storage = chat_agent

    agent.cache.get_cached_response = AsyncMock(return_value=None)
    agent._handle_count_request = AsyncMock(return_value=ChatResponse("Total", {}))

    response = asyncio.run(agent.generate_response("session", "Qual a quantidade total?", context={}))

    agent.cache.get_cached_response.assert_not_awaited()
    agent._handle_count_request.assert_awaited_once()
    assert response.content == "Total"


@pytest.mark.parametrize(
    "query,handler_attr",
    [
        ("Quero um resumo dos documentos", "_handle_summary_request"),
        ("Liste os documentos recentes", "_handle_list_request"),
        ("Preciso de detalhes do documento 123", "_handle_specific_search"),
    ],
)
def test_generate_response_dispatch(monkeypatch, chat_agent, query, handler_attr):
    agent, storage = chat_agent
    agent.cache.get_cached_response = AsyncMock(return_value=None)

    handler = AsyncMock(return_value=ChatResponse("ok", {}))
    monkeypatch.setattr(agent, handler_attr, handler)

    response = asyncio.run(agent.generate_response("session", query, context={}))

    handler.assert_awaited_once()
    assert response.content == "ok"
