"""
Chat Agent for LLM-powered Q&A system.

This module provides intelligent chat capabilities that can:
- Answer questions about processed documents
- Analyze CSV data and provide insights
- Cache responses to save tokens
- Maintain conversation context
"""
import json
import hashlib
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import uuid
import logging

import google.generativeai as genai

from config import GOOGLE_API_KEY, SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    """Response from chat agent."""
    content: str
    metadata: Dict[str, Any]
    cached: bool = False
    tokens_used: Optional[int] = None


@dataclass
class DocumentContext:
    """Context information from documents."""
    documents: List[Dict[str, Any]]
    summaries: List[str]
    insights: List[Dict[str, Any]]


class DocumentSearchEngine:
    """Search and retrieve relevant document context."""

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    async def search_documents(
        self,
        query: str,
        limit: int = 5,
        document_types: Optional[List[str]] = None
    ) -> DocumentContext:
        """Search for relevant documents based on query."""

        # Search in document summaries and insights
        search_query = """
        SELECT
            fd.id,
            fd.file_name,
            fd.document_type,
            fd.document_number,
            fd.issuer_cnpj,
            fd.extracted_data,
            fd.classification,
            ds.summary_text,
            ds.key_insights,
            ai.insight_text,
            ai.insight_type,
            ai.confidence_score
        FROM fiscal_documents fd
        LEFT JOIN document_summaries ds ON fd.id = ds.fiscal_document_id
        LEFT JOIN analysis_insights ai ON fd.id = ai.fiscal_document_id
        WHERE
            (fd.extracted_data::text ILIKE %s OR
             ds.summary_text ILIKE %s OR
             ai.insight_text ILIKE %s)
        """

        params = [f'%{query}%', f'%{query}%', f'%{query}%']

        if document_types:
            search_query += " AND fd.document_type = ANY(%s)"
            params.append(document_types)

        search_query += f" ORDER BY ai.confidence_score DESC NULLS LAST LIMIT {limit}"

        try:
            result = self.supabase.table('fiscal_documents').select(
                'id, file_name, document_type, document_number, issuer_cnpj, extracted_data, classification'
            ).execute()

            documents = result.data if result.data else []

            # Get summaries
            summary_result = self.supabase.table('document_summaries').select(
                'fiscal_document_id, summary_text, key_insights'
            ).in_('fiscal_document_id', [doc['id'] for doc in documents]).execute()

            summaries = [item['summary_text'] for item in summary_result.data if item['summary_text']]

            # Get insights
            insights_result = self.supabase.table('analysis_insights').select(
                'fiscal_document_id, insight_text, insight_type, insight_category, confidence_score'
            ).in_('fiscal_document_id', [doc['id'] for doc in documents]).execute()

            insights = insights_result.data if insights_result.data else []

            return DocumentContext(
                documents=documents,
                summaries=summaries,
                insights=insights
            )

        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return DocumentContext(documents=[], summaries=[], insights=[])


class AnalysisCache:
    """Cache system to avoid redundant LLM calls."""

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def _generate_cache_key(self, query: str, context: Dict[str, Any]) -> str:
        """Generate a unique cache key for query + context."""
        context_str = json.dumps(context, sort_keys=True)
        combined = f"{query}|{context_str}"
        return hashlib.sha256(combined.encode()).hexdigest()

    async def get_cached_response(
        self,
        query: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get cached response if available and not expired."""

        cache_key = self._generate_cache_key(query, context)

        try:
            result = self.supabase.table('analysis_cache').select('*').eq(
                'cache_key', cache_key
            ).gte('expires_at', datetime.now().isoformat()).execute()

            if result.data and len(result.data) > 0:
                cache_entry = result.data[0]
                return {
                    'content': cache_entry['response_content'],
                    'metadata': cache_entry['response_metadata'],
                    'cached': True
                }

        except Exception as e:
            logger.error(f"Error retrieving cache: {e}")

        return None

    async def cache_response(
        self,
        query: str,
        context: Dict[str, Any],
        response: str,
        metadata: Dict[str, Any],
        query_type: str = 'general'
    ) -> None:
        """Cache the response for future use."""

        cache_key = self._generate_cache_key(query, context)

        try:
            self.supabase.table('analysis_cache').insert({
                'cache_key': cache_key,
                'query_type': query_type,
                'query_text': query,
                'context_data': context,
                'response_content': response,
                'response_metadata': metadata,
                'expires_at': (datetime.now() + timedelta(days=7)).isoformat()
            }).execute()

        except Exception as e:
            logger.error(f"Error caching response: {e}")


class ChatAgent:
    """Main chat agent that coordinates LLM interactions."""

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.search_engine = DocumentSearchEngine(supabase_client)
        self.cache = AnalysisCache(supabase_client)

        # Initialize Gemini
        if not GOOGLE_API_KEY:
            logger.error("GOOGLE_API_KEY not configured")
            self.model = None
        else:
            genai.configure(api_key=GOOGLE_API_KEY)
            self.model = genai.GenerativeModel('gemini-pro')

        # Simple conversation history (replaces deprecated LangChain memory)
        self.conversation_history = {}

        # System prompt
        self.system_prompt = """
        Você é um assistente especializado em análise de documentos fiscais e dados empresariais.

        Suas capacidades incluem:
        - Analisar documentos fiscais (NFe, NFCe, CTe)
        - Fornecer insights sobre dados financeiros e tributários
        - Identificar padrões e tendências nos dados
        - Responder perguntas sobre compliance fiscal
        - Analisar planilhas CSV com dados de vendas/compras

        Sempre responda de forma clara, precisa e baseada nos dados fornecidos.
        Se não tiver informações suficientes, seja honesto sobre as limitações.

        Responda em português brasileiro.
        """

    async def create_session(self, session_name: str = None) -> str:
        """Create a new chat session."""

        try:
            result = self.supabase.table('chat_sessions').insert({
                'session_name': session_name or f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                'is_active': True
            }).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]['id']
            else:
                raise Exception("Failed to create chat session")

        except Exception as e:
            logger.error(f"Error creating chat session: {e}")
            raise

    async def save_message(
        self,
        session_id: str,
        message_type: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> None:
        """Save a message to the chat session."""

        try:
            self.supabase.table('chat_messages').insert({
                'session_id': session_id,
                'message_type': message_type,
                'content': content,
                'metadata': metadata or {}
            }).execute()

        except Exception as e:
            logger.error(f"Error saving message: {e}")

    async def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for display."""
        try:
            result = self.supabase.table('chat_messages').select('*').eq(
                'session_id', session_id
            ).order('created_at').execute()

            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []

    async def get_conversation_context(self, session_id: str) -> str:
        """Get conversation history as context for the LLM."""
        try:
            result = self.supabase.table('chat_messages').select('*').eq(
                'session_id', session_id
            ).order('created_at', desc=True).limit(10).execute()

            if not result.data:
                return "Esta é uma nova conversa."

            # Format recent messages for context
            context_lines = []
            for msg in result.data[:5]:  # Last 5 messages
                msg_type = "Usuário" if msg['message_type'] == 'user' else "Assistente"
                context_lines.append(f"{msg_type}: {msg['content']}")

            # Reverse to show chronological order
            context_lines.reverse()

            return "Histórico da conversa:\n" + "\n".join(context_lines)

        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return "Erro ao carregar histórico da conversa."

    async def generate_response(
        self,
        session_id: str,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ChatResponse:
        """Generate a response using LLM with caching and context."""

        # Check if Gemini is available
        if not self.model:
            error_message = "API do Google Gemini não configurada. Verifique se a GOOGLE_API_KEY está definida em .streamlit/secrets.toml"
            await self.save_message(session_id, 'assistant', error_message, {'error': True})
            return ChatResponse(
                content=error_message,
                metadata={'error': True, 'error_type': 'missing_api_key'},
                cached=False
            )

        # Check cache first
        if context:
            cached = await self.cache.get_cached_response(query, context)
            if cached:
                await self.save_message(session_id, 'assistant', cached['content'],
                                      {'cached': True, 'tokens_used': 0})
                return ChatResponse(
                    content=cached['content'],
                    metadata=cached['metadata'],
                    cached=True
                )

        # Get relevant document context
        document_context = DocumentContext(documents=[], summaries=[], insights=[])
        if context and 'document_types' in context:
            document_context = await self.search_engine.search_documents(
                query=query,
                limit=context.get('limit', 5),
                document_types=context.get('document_types')
            )

        # Get conversation history for context
        history_context = await self.get_conversation_context(session_id)

        # Prepare context for LLM
        context_prompt = self._prepare_context_prompt(query, document_context, context, history_context)

        # Generate response
        full_prompt = f"{self.system_prompt}\n\n{context_prompt}\n\nQuery: {query}"

        try:
            response = self.model.generate_content(full_prompt)

            # Extract response content and metadata
            content = response.text
            metadata = {
                'model': 'gemini-pro',
                'timestamp': datetime.now().isoformat(),
                'tokens_used': getattr(response, 'usage_metadata', {}).get('total_token_count', 0)
            }

            # Cache the response
            if context:
                await self.cache.cache_response(
                    query=query,
                    context=context,
                    response=content,
                    metadata=metadata,
                    query_type=context.get('query_type', 'general')
                )

            # Save to conversation history
            await self.save_message(session_id, 'assistant', content, metadata)

            return ChatResponse(
                content=content,
                metadata=metadata,
                cached=False,
                tokens_used=metadata['tokens_used']
            )

        except Exception as e:
            error_message = f"Desculpe, ocorreu um erro ao processar sua pergunta: {str(e)}"
            await self.save_message(session_id, 'assistant', error_message, {'error': True})
            return ChatResponse(
                content=error_message,
                metadata={'error': True, 'error_message': str(e)},
                cached=False
            )

    def _prepare_context_prompt(
        self,
        query: str,
        document_context: DocumentContext,
        context: Optional[Dict[str, Any]],
        history_context: str = ""
    ) -> str:
        """Prepare context information for the LLM prompt."""

        context_parts = []

        # Add conversation history
        if history_context and history_context != "Esta é uma nova conversa.":
            context_parts.append(f"Contexto da conversa anterior:\n{history_context}")

        # Add document context
        if document_context.documents:
            context_parts.append("Documentos relevantes encontrados:")
            for doc in document_context.documents[:3]:  # Limit to 3 documents
                context_parts.append(f"- {doc['file_name']} (Tipo: {doc.get('document_type', 'N/A')})")
                if doc.get('extracted_data'):
                    # Extract key information
                    data = doc['extracted_data']
                    if data.get('emitente'):
                        context_parts.append(f"  Emitente: {data['emitente'].get('razao_social', 'N/A')}")
                    if data.get('total'):
                        context_parts.append(f"  Valor: R$ {data['total']:.2f}")

        # Add summaries
        if document_context.summaries:
            context_parts.append("\nResumos dos documentos:")
            for summary in document_context.summaries[:2]:  # Limit to 2 summaries
                context_parts.append(f"- {summary}")

        # Add insights
        if document_context.insights:
            insights_by_type = {}
            for insight in document_context.insights:
                insight_type = insight.get('insight_type', 'general')
                if insight_type not in insights_by_type:
                    insights_by_type[insight_type] = []
                insights_by_type[insight_type].append(insight['insight_text'])

            context_parts.append("\nInsights identificados:")
            for insight_type, insights in insights_by_type.items():
                context_parts.append(f"{insight_type.title()}:")
                for insight in insights[:3]:  # Limit to 3 insights per type
                    context_parts.append(f"- {insight}")

        # Add CSV context if provided
        if context and context.get('csv_data'):
            context_parts.append(f"\nDados do CSV fornecido: {context['csv_data']}")

        return "\n".join(context_parts) if context_parts else "Nenhum contexto específico disponível."
