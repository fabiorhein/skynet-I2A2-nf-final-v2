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
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import uuid
import logging
import re

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

import os
import sys

# Adiciona o diretório raiz ao path para garantir que as importações funcionem
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from config import GOOGLE_API_KEY, SUPABASE_URL, SUPABASE_KEY
except ImportError:
    # Tenta carregar do ambiente ou secrets do Streamlit
    import os
    import streamlit as st
    
    # Tenta obter do ambiente ou do secrets do Streamlit
    def get_config_value(key, default=None):
        return os.getenv(key) or getattr(st.secrets, key, default) if hasattr(st, 'secrets') else os.getenv(key, default)
    
    GOOGLE_API_KEY = get_config_value('GOOGLE_API_KEY')
    SUPABASE_URL = get_config_value('SUPABASE_URL') or get_config_value('connections.supabase.URL')
    SUPABASE_KEY = get_config_value('SUPABASE_KEY') or get_config_value('connections.supabase.KEY')

from backend.services.document_analyzer import DocumentAnalyzer
from backend.database.storage_manager import storage_manager, get_async_storage

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

    def __init__(self, storage):
        self.storage = storage

    async def search_documents(
        self,
        query: str,
        limit: int = 5,
        document_types: Optional[List[str]] = None
    ) -> DocumentContext:
        """Search for relevant documents based on query."""

        try:
            # Use storage to get all documents and filter by query
            all_docs = await self.storage.get_fiscal_documents(page=1, page_size=1000)

            # Filter documents containing the query
            filtered_docs = []
            for doc in all_docs.items:
                if self._document_matches_query(doc, query):
                    filtered_docs.append(doc)

            # Limit results
            documents = filtered_docs[:limit]

            # Get summaries for these documents
            summaries = []
            insights = []

            for doc in documents:
                # Get document summaries if available
                doc_summaries = await self.storage.get_fiscal_documents(
                    id=doc['id'], page=1, page_size=1
                )
                if doc_summaries.items:
                    # Extract summary text from document data (if stored)
                    pass

                # Get analysis insights for this document
                doc_insights = await self.storage.get_fiscal_documents(
                    id=doc['id'], page=1, page_size=1
                )
                if doc_insights.items and doc_insights.items[0].get('classification'):
                    # Extract insights from classification data
                    pass

            return DocumentContext(
                documents=documents,
                summaries=summaries,
                insights=insights
            )

        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return DocumentContext(documents=[], summaries=[], insights=[])

    def _document_matches_query(self, document: Dict[str, Any], query: str) -> bool:
        """Check if document matches the search query."""
        query_lower = query.lower()
        extracted_data = document.get('extracted_data', {})

        # Search in various fields
        search_fields = [
            extracted_data.get('emitente', {}).get('razao_social', ''),
            extracted_data.get('emitente', {}).get('cnpj', ''),
            extracted_data.get('destinatario', {}).get('razao_social', ''),
            extracted_data.get('destinatario', {}).get('cnpj', ''),
            document.get('file_name', ''),
            document.get('document_number', ''),
            str(extracted_data)
        ]

        return any(query_lower in str(field).lower() for field in search_fields)


class AnalysisCache:
    """Cache system to avoid redundant LLM calls."""

    def __init__(self, storage):
        self.storage = storage

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
            cache_entry = self.storage.get_analysis_cache(cache_key)

            if cache_entry:
                return cache_entry

        except Exception as e:
            logger.error(f"Error retrieving cache: {e}")

        return None

    async def cache_response(
        self,
        query: str,
        context: Dict[str, Any],
        response: str,
        metadata: Dict[str, Any],
        query_type: str = 'general',
        session_id: Optional[str] = None
    ) -> None:
        """Cache the response for future use."""

        cache_key = self._generate_cache_key(query, context)
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()

        try:
            self.storage.save_analysis_cache(
                cache_key=cache_key,
                query_type=query_type,
                query_text=query,
                context_data=context,
                response_content=response,
                response_metadata=metadata,
                expires_at=expires_at,
                session_id=session_id
            )

        except Exception as e:
            logger.error(f"Error caching response: {e}")


class ChatAgent:
    """Main chat agent that coordinates LLM interactions."""

    def __init__(self, storage):
        self.storage = storage
        self.search_engine = DocumentSearchEngine(storage)
        self.cache = AnalysisCache(storage)
        self.document_analyzer = DocumentAnalyzer(storage)

        # Initialize Gemini
        if not GOOGLE_API_KEY:
            logger.error("GOOGLE_API_KEY not configured")
            self.model = None
        else:
            # Configuração do modelo Gemini - tentar 2.0-flash primeiro, depois 1.5-flash
            try:
                # Tentar modelo mais avançado primeiro
                model_name = 'gemini-2.0-flash-exp'
                try:
                    self.model = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=GOOGLE_API_KEY,
                        temperature=0.0,
                        request_timeout=30
                    )
                    self.model_name = model_name
                    logger.info(f"✅ Successfully initialized Gemini model: {model_name}")
                except Exception as e:
                    logger.warning(f"Gemini 2.0-flash not available: {e}")
                    # Fallback para 1.5-flash
                    model_name = 'gemini-1.5-flash'
                    self.model = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=GOOGLE_API_KEY,
                        temperature=0.0,
                        request_timeout=30
                    )
                    self.model_name = model_name
                    logger.info(f"✅ Successfully initialized fallback Gemini model: {model_name}")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Failed to initialize Gemini models: {error_msg}")
                if "quota" in error_msg.lower() or "429" in error_msg:
                    friendly_msg = (
                        "Limite de quota da API do Gemini excedido.\n\n"
                        "🔄 **Verifique seu plano e tente novamente:**\n"
                        "1. Acesse: https://ai.google.dev/gemini-api/docs/rate-limits\n"
                        "2. Considere usar uma chave API diferente\n"
                        "3. Aguarde a liberação da quota (geralmente 1-2 horas)\n\n"
                        "💡 Alternativamente, configure uma chave API do OpenAI em .streamlit/secrets.toml"
                    )
                else:
                    friendly_msg = (
                        "Erro ao inicializar modelos Gemini.\n\n"
                        "💡 Para resolver:\n"
                        "1. Verifique se a GOOGLE_API_KEY está correta em .streamlit/secrets.toml\n"
                        "2. Certifique-se de que sua conta tem acesso aos modelos Gemini\n"
                        "3. Considere usar uma chave API do OpenAI como alternativa"
                    )
                raise Exception(friendly_msg) from e

        # Simple conversation history (replaces deprecated LangChain memory)
        self.conversation_history = {}

        # System prompt
        self.system_prompt = """
        Você é um assistente especialista em documentos fiscais brasileiros. Responda sempre em português de forma clara, precisa e útil.

        **Diretrizes Gerais:**
        1. Use os dados fornecidos pelo sistema para responder com 100% de precisão
        2. Seja específico com números, quantidades e valores
        3. Use formatação markdown para melhorar a legibilidade
        4. Responda de forma natural e conversacional
        5. Foque nos dados reais, não em conhecimento geral

        **Para perguntas sobre contagem:**
        - Destaque o total de documentos
        - Mencione o valor total se disponível
        - Inclua distribuição por categoria com percentuais
        - Seja direto e informativo

        **Para pedidos de lista:**
        - Apresente os documentos de forma organizada
        - Inclua tipo, emissor, valor e data quando disponível
        - Use tabelas ou listas numeradas para clareza
        - Mencione se está mostrando apenas parte dos documentos

        **Para resumos/categorias:**
        - Foque na distribuição por tipo de documento
        - Inclua percentuais para cada categoria
        - Mencione os principais emissores
        - Destaque padrões ou observações relevantes

        **Para perguntas específicas:**
        - Use o contexto fornecido para responder
        - Seja preciso com os dados disponíveis
        - Explique se alguma informação não está disponível

        Responda sempre baseado nos dados fornecidos, não invente informações.
        """

    async def create_session(self, session_name: str = None) -> str:
        """Create a new chat session."""

        try:
            session = self.storage.create_chat_session(session_name)
            return session['id']

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
            self.storage.save_chat_message(session_id, message_type, content, metadata or {})

        except Exception as e:
            logger.error(f"Error saving message: {e}")

    async def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for display."""
        try:
            messages = self.storage.get_chat_messages(session_id, limit=50)
            # Convert to the format expected by the frontend
            return messages

        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []

    async def get_conversation_context(self, session_id: str) -> str:
        """Get conversation history as context for the LLM."""
        try:
            return self.storage.get_chat_context(session_id, limit=5)

        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return "Erro ao carregar histórico da conversa."

    async def _get_document_summary(self, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Obtém um resumo dos documentos com base nos filtros fornecidos."""
        return await self.document_analyzer.get_documents_summary(filters)

    async def _get_all_documents_summary(self, time_filter=None) -> Dict[str, Any]:
        """
        Obtém um resumo dos documentos para análise de categorias.
        
        Args:
            time_filter: Filtra documentos criados após esta data/hora.
                        Se None, retorna todos os documentos.
        """
        return await self.document_analyzer.get_all_documents_summary(time_filter=time_filter)

    def _is_summary_request(self, query: str) -> bool:
        """Verifica se a pergunta é sobre resumo/categorias de documentos."""
        query_lower = query.lower()
        summary_keywords = [
            'resumo', 'categorias', 'tipos de documentos', 'distribuição',
            'quantos documentos', 'quais categorias', 'quais tipos',
            'visão geral', 'análise geral', 'estatísticas', 'estatistica',
            'estatísticas dos documentos', 'estatistica dos documentos',
            'resumo dos documentos', 'categorias de documentos', 'tipos de nota',
            'quais são as categorias', 'quantos de cada tipo', 'distribuição de documentos'
        ]
        count_keywords = [
            'quantidade total', 'quantos documentos', 'quantas notas',
            'total de notas', 'número total', 'contagem total'
        ]
        list_keywords = ['lista', 'listar', 'todos os documentos', 'todas as notas', 'me traga uma lista']

        has_summary = any(keyword in query_lower for keyword in summary_keywords)
        has_count = any(keyword in query_lower for keyword in count_keywords)
        has_list = any(keyword in query_lower for keyword in list_keywords)

        return has_summary and not has_count and not has_list

    def _is_list_request(self, query: str) -> bool:
        """Verifica se a consulta é um pedido de listagem de documentos."""
        query_lower = query.lower()

        list_keywords = [
            'listar', 'lista', 'quais são', 'mostrar documentos', 'ver documentos',
            'listar documentos', 'documentos fiscais', 'notas fiscais', 'mostrar notas',
            'quero ver', 'quais notas', 'quais documentos', 'listar notas', 'mostrar nota',
            'documents list', 'invoice list', 'list invoices'
        ]

        recent_keywords = [
            'últimas notas', 'notas recentes', 'últimos documentos',
            'documentos recentes', 'notas fiscais recentes', 'últimas notas fiscais',
            'mais recentes', 'notas mais recentes', 'documentos mais recentes',
            'últimos lançamentos', '10 últimas notas', 'dez últimas notas',
            'últimos registros', 'registros recentes'
        ]

        analysis_keywords = [
            'análise criteriosa', 'análise detalhada', 'análise completa',
            'insights', 'recomendações', 'pontos de atenção', 'resumo crítico',
            'panorama', 'diagnóstico', 'sugestões'
        ]

        # Novas palavras-chave para perguntas sobre valores e características
        value_keywords = [
            'maior valor', 'menor valor', 'valor mais alto', 'valor mais baixo',
            'mais caro', 'mais barato', 'qual o maior', 'qual o menor',
            'valor máximo', 'valor mínimo', 'nota mais cara', 'nota mais barata',
            'documento mais caro', 'documento mais barato', 'com maior valor',
            'com menor valor', 'valor total', 'qual a nota', 'qual o documento'
        ]

        return any(keyword in query_lower for keyword in 
                  list_keywords + recent_keywords + analysis_keywords + value_keywords)

    def _get_query_intent(self, query: str) -> str:
        query_lower = query.lower()

        analysis_keywords = [
            'análise criteriosa', 'análise detalhada', 'análise completa',
            'insights', 'recomendações', 'pontos de atenção', 'resumo crítico',
            'panorama', 'diagnóstico', 'sugestões'
        ]

        recent_keywords = [
            'últimas notas', 'notas recentes', 'últimos documentos',
            'documentos recentes', 'notas fiscais recentes', 'últimas notas fiscais',
            'mais recentes', 'notas mais recentes', 'documentos mais recentes',
            'últimos lançamentos', 'últimas entradas', 'últimos registros'
        ]

        if any(keyword in query_lower for keyword in analysis_keywords):
            return 'analysis'
        if any(keyword in query_lower for keyword in recent_keywords):
            return 'recent'
        return 'generic'

    def _is_count_request(self, query: str) -> bool:
        """Verifica se a pergunta é sobre contagem específica."""
        query_lower = query.lower()
        count_keywords = [
            'quantidade total', 'quantos documentos', 'quantas notas',
            'total de notas', 'número total', 'contagem total'
        ]

        return any(keyword in query_lower for keyword in count_keywords)

    def _prepare_summary_prompt(self, query: str, summary_data: Dict[str, Any]) -> str:
        """Prepara o contexto para perguntas de resumo de documentos."""
        context_parts = []

        # Informações básicas
        total_docs = summary_data['total_documents']
        context_parts.append(f"📊 **Informações do Banco de Dados:**")
        context_parts.append(f"- Total de documentos: **{total_docs}**")
        context_parts.append(f"- Valor total dos documentos: **R$ {summary_data['total_value']:,.2f}**")
        context_parts.append("")

        # Categorias por tipo
        if summary_data['by_type']:
            context_parts.append("📋 **Distribuição por Categoria:**")
            for category, count in summary_data['by_type'].items():
                percentage = (count / total_docs) * 100 if total_docs > 0 else 0
                context_parts.append(f"- **{category}**: {count} documentos ({percentage:.1f}%)")

        # Emissores principais
        if summary_data['by_issuer']:
            context_parts.append("")
            context_parts.append("🏢 **Principais Emissores:**")
            sorted_issuers = sorted(summary_data['by_issuer'].items(), key=lambda x: x[1], reverse=True)
            for issuer, count in sorted_issuers[:5]:  # Top 5 emissores
                context_parts.append(f"- **{issuer}**: {count} documentos")

        # Instruções para resposta
        context_parts.append("")
        context_parts.append("📝 **Instruções para a resposta:**")
        context_parts.append("1. Use os dados fornecidos para criar um resumo preciso")
        context_parts.append("2. Apresente as informações em formato de tabela quando apropriado")
        context_parts.append("3. Seja específico sobre quantidades e categorias")
        context_parts.append("4. Destaque informações importantes em negrito")
        context_parts.append("5. Responda sempre em português claro e objetivo")

        return "\n".join(context_parts)

    async def _search_documents(self, query: str, limit: int = 5) -> List[Dict]:
        """Busca documentos relevantes usando busca semântica."""
        return await self.document_analyzer.search_documents(query, limit)

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
        cached_info: Optional[Dict[str, Any]] = None
        if context:
            cached_info = await self.cache.get_cached_response(query, context)
            if cached_info:
                cached_session = cached_info.get('cached_session_id')
                cached_content = cached_info.get('content', '')
                cached_metadata = cached_info.get('metadata', {})
                cached_time = cached_info.get('cached_at')

                if cached_session and cached_session == session_id:
                    annotated_content = "🔁 **Pergunta repetida nesta sessão**\n\n" \
                        "Reaproveitando a resposta anterior e mantendo o histórico da conversa.\n\n" \
                        f"{cached_content}"
                    metadata = {
                        **cached_metadata,
                        'cached': True,
                        'cached_session_id': cached_session,
                        'cached_at': cached_time,
                        'tokens_used': 0,
                        'reused_in_session': True
                    }
                    await self.save_message(session_id, 'assistant', annotated_content, metadata)
                    return ChatResponse(
                        content=annotated_content,
                        metadata=metadata,
                        cached=True
                    )
                else:
                    # Cache pertence a outra sessão – continuar processamento normal
                    cached_info = None

        # Get relevant document context
        document_context = DocumentContext(documents=[], summaries=[], insights=[])

        try:
            # Determinar o tipo de pergunta e responder adequadamente
            if self._is_count_request(query):
                # Para perguntas sobre contagem total
                return await self._handle_count_request(session_id, query)

            elif self._is_list_request(query):
                # Para perguntas sobre lista de documentos
                return await self._handle_list_request(session_id, query)

            elif self._is_summary_request(query):
                # Para perguntas sobre resumo/categorias
                return await self._handle_summary_request(session_id, query)

            else:
                # Para perguntas específicas ou gerais - usar busca normal
                return await self._handle_specific_search(session_id, query, context)

        except Exception as e:
            logger.error(f"Erro ao processar pergunta: {e}")
            # Fallback para busca genérica
            return await self._handle_specific_search(session_id, query, context)

    async def _handle_count_request(self, session_id: str, query: str) -> ChatResponse:
        """Handle requests for document counts using LLM for natural response."""
        try:
            summary_data = await self._get_all_documents_summary()

            if not summary_data or summary_data['total_documents'] == 0:
                # Use Gemini for natural response even when no documents
                prompt = f"""O usuário perguntou sobre a quantidade de documentos no banco de dados.

**Dados encontrados:**
- Total de documentos: 0
- Não há documentos para análise

Por favor, responda de forma natural e informativa sobre a ausência de documentos no sistema."""
            else:
                # Prepare raw data for Gemini
                total = summary_data['total_documents']
                total_value = summary_data['total_value']
                categories = summary_data['by_type']
                issuers = summary_data['by_issuer']

                prompt = f"""O usuário perguntou sobre a quantidade total de documentos no banco de dados.

**Dados brutos do banco:**
- Total de documentos fiscais: {total}
- Valor total dos documentos: R$ {total_value:,.2f}
- Número de categorias diferentes: {len(categories)}
- Número de emissores diferentes: {len(issuers)}

**Categorias encontradas:**
"""
                for category, count in categories.items():
                    percentage = (count / total) * 100
                    prompt += f"- {category}: {count} documentos ({percentage:.1f}%)\n"

                prompt += f"""
**Principais emissores:**
"""
                sorted_issuers = sorted(issuers.items(), key=lambda x: x[1], reverse=True)
                for issuer, count in sorted_issuers[:5]:
                    prompt += f"- {issuer}: {count} documentos\n"

                prompt += f"""

**Instruções:**
Responda de forma natural e conversacional, como se estivesse falando diretamente com o usuário.
Use os dados fornecidos para dar uma resposta precisa e útil.
Estruture a resposta de forma clara, usando negrito para destacar números importantes.
Seja específico sobre quantidades e categorias encontradas.
Responda em português."""

            # Send to Gemini for natural formatting
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ]

            response = self.model.invoke(messages, config={
                'temperature': 0.1,
                'max_tokens': 800,
                'top_p': 0.9,
                'frequency_penalty': 0.3,
                'presence_penalty': 0.3
            })

            content = response.content if hasattr(response, 'content') else str(response)
            content = self._clean_response_content(content)

            # Create metadata
            metadata = {
                'model': self.model_name or 'unknown',
                'timestamp': datetime.now().isoformat(),
                'tokens_used': len(content.split()),
                'query_type': 'count',
                'raw_data': summary_data
            }

            await self.save_message(session_id, 'assistant', content, metadata)

            return ChatResponse(
                content=content,
                metadata=metadata,
                cached=False,
                tokens_used=metadata['tokens_used']
            )

        except Exception as e:
            error_message = f"Erro ao buscar contagem de documentos: {str(e)}"
            await self.save_message(session_id, 'assistant', error_message, {'error': True})
            return ChatResponse(content=error_message, metadata={'error': True}, cached=False)

    def _get_metadata_template(self, is_recent_query: bool = False, error: bool = False) -> Dict[str, Any]:
        """Return a standardized metadata template.
        
        Args:
            is_recent_query: Whether this is a recent documents query
            error: Whether this is an error response
            
        Returns:
            Dict with standardized metadata structure
        """
        return {
            'model': 'system' if error else (self.model_name or 'unknown'),
            'timestamp': datetime.now().isoformat(),
            'tokens_used': 0,
            'query_type': 'error' if error else ('recent_documents' if is_recent_query else 'list'),
            'document_count': 0,
            'total_documents': 0,
            'is_recent_query': is_recent_query,
            **({'error': True} if error else {})
        }

    async def _handle_list_request(self, session_id: str, query: str) -> ChatResponse:
        """Handle requests for document lists using LLM for natural response."""
        try:
            query_lower = query.lower()
            time_filter = None

            intent = self._get_query_intent(query)
            is_recent_query = intent == 'recent'
            is_analysis_request = intent == 'analysis'

            # Detecta se é uma pergunta sobre valores extremos
            is_value_query = any(keyword in query_lower for keyword in [
                'maior valor', 'menor valor', 'valor mais alto', 'valor mais baixo',
                'mais caro', 'mais barato', 'valor máximo', 'valor mínimo',
                'nota mais cara', 'nota mais barata', 'documento mais caro', 'documento mais barato'
            ])

            # Verifica se há um filtro de tempo específico na consulta
            import re
            from datetime import datetime, timedelta
            
            time_patterns = [
                (r'(\d+)\s*minutos?\s*atrás', 'minutes'),
                (r'(\d+)\s*horas?\s*atrás', 'hours'),
                (r'(\d+)\s*dias?\s*atrás', 'days'),
                (r'(\d+)\s*semanas?\s*atrás', 'weeks'),
                (r'últimos?\s*(\d+)\s*minutos?', 'minutes'),
                (r'últimas?\s*(\d+)\s*horas?', 'hours'),
                (r'últimos?\s*(\d+)\s*dias?', 'days'),
                (r'últimas?\s*(\d+)\s*semanas?', 'weeks'),
                (r'nos\s*últimos?\s*(\d+)\s*minutos?', 'minutes'),
                (r'nas\s*últimas?\s*(\d+)\s*horas?', 'hours'),
                (r'nos\s*últimos?\s*(\d+)\s*dias?', 'days'),
                (r'nas\s*últimas?\s*(\d+)\s*semanas?', 'weeks'),
            ]
            
            doc_limit = None

            for pattern, unit in time_patterns:
                match = re.search(pattern, query_lower)
                if match:
                    value = int(match.group(1))
                    delta = timedelta(**{unit: value})
                    time_filter = datetime.now() - delta
                    is_recent_query = True
                    break

            # Detect explicit quantity requests (e.g., "5 últimos documentos")
            quantity_patterns = [
                r'(?:os|as)?\s*(\d+)\s*(?:últimos|últimas|mais\s+recentes|recentes)',
                r'(?:listar|mostrar)\s*(\d+)\s*(?:documentos|notas)'
            ]

            for quantity_pattern in quantity_patterns:
                match = re.search(quantity_pattern, query_lower)
                if match:
                    try:
                        doc_limit = max(1, int(match.group(1)))
                        break
                    except ValueError:
                        continue

            if doc_limit is None:
                number_words = {
                    'um': 1, 'uma': 1,
                    'dois': 2, 'duas': 2,
                    'três': 3, 'tres': 3,
                    'quatro': 4,
                    'cinco': 5,
                    'seis': 6,
                    'sete': 7,
                    'oito': 8,
                    'nove': 9,
                    'dez': 10,
                    'quinze': 15
                }
                for word, value in number_words.items():
                    if word in query_lower and any(trigger in query_lower for trigger in ['últimos', 'últimas', 'recentes']) and value:
                        doc_limit = value
                        break
            
            # Busca os documentos com ordenação por data e filtro de tempo
            summary_data = await self._get_all_documents_summary(time_filter=time_filter)
            documents_to_show = []  # Initialize as empty list
            total = 0
            
            if not summary_data or summary_data['total_documents'] == 0:
                # Return early with a friendly message when no documents are found
                message = "📭 Não foram encontrados documentos no sistema com os critérios fornecidos."
                metadata = self._get_metadata_template(is_recent_query=is_recent_query)
                await self.save_message(session_id, 'assistant', message, metadata)
                return ChatResponse(content=message, metadata=metadata, cached=False)
            else:
                # Prepara os dados brutos para o Gemini
                total = summary_data['total_documents']
                documents = summary_data['documents']
                
                # Ordena os documentos baseado no tipo de consulta
                if is_value_query:
                    # Para perguntas sobre valores, ordena por valor (do maior para o menor)
                    # Primeiro filtra documentos que têm valor válido
                    documents_with_value = []
                    for doc in documents:
                        if doc.get('extracted_data'):
                            try:
                                data = doc['extracted_data']
                                if isinstance(data, str):
                                    data = json.loads(data)
                                if isinstance(data, dict):
                                    value = data.get('total', data.get('valor_total', data.get('value', None)))
                                    if value is not None and value != 'N/A':
                                        try:
                                            value = float(value)
                                            doc['_sort_value'] = value
                                            documents_with_value.append(doc)
                                        except (ValueError, TypeError):
                                            pass
                            except Exception:
                                pass
                    
                    # Se encontrou documentos com valor, ordena por valor
                    if documents_with_value:
                        # Verifica se é pergunta sobre maior ou menor valor
                        is_max_value = any(keyword in query_lower for keyword in [
                            'maior valor', 'valor mais alto', 'mais caro', 'valor máximo', 
                            'nota mais cara', 'documento mais caro'
                        ])
                        
                        if is_max_value:
                            documents_sorted = sorted(documents_with_value, key=lambda x: x['_sort_value'], reverse=True)
                        else:
                            documents_sorted = sorted(documents_with_value, key=lambda x: x['_sort_value'])
                    else:
                        # Fallback para ordenação por data se não conseguir extrair valores
                        documents_sorted = sorted(
                            documents, 
                            key=lambda x: x.get('created_at', ''), 
                            reverse=True
                        )
                else:
                    # Ordenação padrão por data de criação (mais recentes primeiro)
                    documents_sorted = sorted(
                        documents, 
                        key=lambda x: x.get('created_at', ''), 
                        reverse=True
                    )
                
                # Para consultas sobre valores extremos, mostra apenas 1 documento por padrão
                if is_value_query and doc_limit is None:
                    default_limit = 1
                elif is_recent_query:
                    default_limit = 10
                else:
                    default_limit = 15
                
                limit = doc_limit if (doc_limit and doc_limit > 0) else default_limit
                documents_to_show = documents_sorted[:limit]

                # Prepara o prompt baseado no tipo de consulta
                base_prompt = []
                if is_analysis_request:
                    base_prompt.append("O usuário pediu uma análise criteriosa dos documentos fiscais importados.")
                    base_prompt.append(
                        "Além de listar os documentos relevantes, forneça uma análise detalhada com: "
                        "principais categorias e emissores, valores agregados, status de processamento "
                        "e recomendações ou próximos passos para o usuário."
                    )
                elif is_value_query:
                    if any(keyword in query_lower for keyword in [
                        'maior valor', 'valor mais alto', 'mais caro', 'valor máximo', 
                        'nota mais cara', 'documento mais caro'
                    ]):
                        base_prompt.append("O usuário quer saber qual é a nota fiscal com o maior valor total.")
                        base_prompt.append("Mostre apenas o documento com o maior valor encontrado.")
                    else:
                        base_prompt.append("O usuário quer saber qual é a nota fiscal com o menor valor total.")
                        base_prompt.append("Mostre apenas o documento com o menor valor encontrado.")
                elif is_recent_query:
                    base_prompt.append("O usuário pediu uma lista com as notas fiscais mais recentes do banco de dados.")
                else:
                    base_prompt.append("O usuário pediu uma lista com documentos fiscais do banco de dados.")

                base_prompt.append("\n**Dados brutos encontrados:**")
                base_prompt.append(f"- Total de documentos: {total}")
                base_prompt.append(f"- Valor total: R$ {summary_data['total_value']:.2f}")

                if is_recent_query:
                    base_prompt.append(f"- Mostrando as {len(documents_to_show)} notas mais recentes")
                else:
                    base_prompt.append(f"- Mostrando {len(documents_to_show)} de {total} documentos")

                if is_analysis_request:
                    # Adiciona visão agregada para embasar a análise
                    by_type = summary_data.get('by_type', {})
                    if by_type:
                        base_prompt.append("\n**Distribuição por tipo:**")
                        for doc_type, count in sorted(by_type.items(), key=lambda item: item[1], reverse=True):
                            percentage = (count / total * 100) if total else 0
                            base_prompt.append(f"- {doc_type}: {count} documentos ({percentage:.1f}%)")

                    by_issuer = summary_data.get('by_issuer', {})
                    if by_issuer:
                        base_prompt.append("\n**Principais emissores:**")
                        for issuer, count in sorted(by_issuer.items(), key=lambda item: item[1], reverse=True)[:5]:
                            percentage = (count / total * 100) if total else 0
                            base_prompt.append(f"- {issuer}: {count} documentos ({percentage:.1f}%)")

                    status_counts: Dict[str, int] = {}
                    for doc in documents:
                        status = (doc.get('validation_status') or 'desconhecido').lower()
                        status_counts[status] = status_counts.get(status, 0) + 1

                    if status_counts:
                        base_prompt.append("\n**Status de processamento:**")
                        for status, count in sorted(status_counts.items(), key=lambda item: item[1], reverse=True):
                            percentage = (count / total * 100) if total else 0
                            base_prompt.append(f"- {status}: {count} documentos ({percentage:.1f}%)")

                    base_prompt.append("\nInclua recomendações práticas com base nesses dados (por exemplo, prioridades de validação ou consolidação financeira).")

                base_prompt.append("")
                prompt = "\n".join(base_prompt)
                
                # Adiciona detalhes de cada documento
                for i, doc in enumerate(documents_to_show, 1):
                    doc_type = doc.get('categorized_type', 'N/A')
                    file_name = doc.get('file_name', 'N/A')
                    cnpj = doc.get('issuer_cnpj', 'N/A')
                    
                    # Formata a data e hora de forma mais amigável
                    created_at = doc.get('created_at')
                    formatted_date = 'Data não disponível'
                    if created_at:
                        try:
                            if isinstance(created_at, datetime):
                                dt = created_at
                            elif isinstance(created_at, str):
                                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            else:
                                dt = None

                            if dt is not None:
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                formatted_date = dt.astimezone(timezone.utc).strftime('%d/%m/%Y às %H:%M')
                            elif isinstance(created_at, str):
                                formatted_date = created_at[:10]
                        except (ValueError, TypeError):
                            if isinstance(created_at, str):
                                formatted_date = created_at[:10]
                    
                    # Extrai o valor
                    value = 'N/A'
                    if doc.get('extracted_data'):
                        try:
                            data = doc['extracted_data']
                            if isinstance(data, str):
                                data = json.loads(data)
                            if isinstance(data, dict):
                                value = data.get('total', data.get('valor_total', data.get('value', 'N/A')))
                                # Formata o valor monetário
                                if value not in ['N/A', None]:
                                    try:
                                        value = float(value)
                                        value = f'R$ {value:,.2f}'.replace('.', 'v').replace(',', '.').replace('v', ',')
                                    except (ValueError, TypeError):
                                        pass
                        except Exception as e:
                            logger.warning(f"Erro ao extrair valor do documento: {e}")
                    
                    # Adiciona detalhes do documento ao prompt
                    prompt += f"{i}. **{doc_type}**\n"
                    prompt += f"   📄 **Arquivo:** {file_name}\n"
                    prompt += f"   🏢 **CNPJ Emissor:** {cnpj}\n"
                    prompt += f"   💰 **Valor:** {value}\n"
                    prompt += f"   📅 **Data/Hora:** {formatted_date}\n"
                    # Adiciona status de validação se disponível
                    if doc.get('validation_status'):
                        status_emoji = '✅' if doc['validation_status'] == 'valid' else '⚠️' if doc['validation_status'] == 'warning' else '❌'
                        prompt += f"   {status_emoji} **Status:** {doc['validation_status'].capitalize()}\n"
                    prompt += "\n"

                if not is_recent_query and total > limit:
                    prompt += f"*(Mostrando apenas os primeiros {limit} documentos. Total no banco: {total})*\n\n"
                elif is_recent_query and len(documents_to_show) < total:
                    prompt += f"*(Mostrando as {len(documents_to_show)} notas mais recentes. Total no banco: {total})*\n\n"

                # Instruções para a IA
                prompt += """**Instruções:**
Responda de forma natural e conversacional, como se estivesse apresentando os documentos para o usuário.
"""
                if is_value_query:
                    prompt += """- Esta é uma pergunta específica sobre valores dos documentos
- Destaque claramente qual é o documento com o valor mais alto/baixo encontrado
- Mostre o valor de forma destacada e formatada corretamente
- Explique que este é o resultado baseado nos dados disponíveis
"""
                elif is_recent_query:
                    prompt += """- Se for uma consulta por notas recentes, destaque que são as mais atuais
"""
                else:
                    prompt += """- Para pedidos de análise criteriosa, vá além da lista: forneça interpretação, destaques e próximos passos
"""

                prompt += """- Inclua informações importantes como tipo, emissor, valor e data/hora
- Formate os valores monetários corretamente (R$ X.XXX,XX)
- Use formatação markdown para melhorar a legibilidade (negrito, itálico, listas)
- Seja específico sobre quantos documentos estão sendo mostrados
- Inclua o total de documentos no banco para referência
- Responda em português"""

            try:
                # Envia para o Gemini para formatação natural
                messages = [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=prompt)
                ]

                response = self.model.invoke(messages, config={
                    'temperature': 0.2,
                    'max_tokens': 2000,  # Aumentado para permitir respostas mais completas
                    'top_p': 0.9,
                    'frequency_penalty': 0.3,
                    'presence_penalty': 0.3
                })

                content = response.content if hasattr(response, 'content') else str(response)
                content = self._clean_response_content(content)

                # Create tracking metadata using the template
                metadata = self._get_metadata_template(is_recent_query=is_recent_query)
                metadata.update({
                    'model': self.model_name or 'unknown',
                    'tokens_used': len(content.split()),
                    'document_count': len(documents_to_show) if documents_to_show else 0,
                    'total_documents': total
                })
            except Exception as e:
                logger.error(f"Erro ao processar resposta do modelo: {str(e)}")
                content = "🔍 Desculpe, ocorreu um erro ao processar sua solicitação. Tente novamente mais tarde."
                metadata = self._get_metadata_template(is_recent_query=is_recent_query, error=True)
                metadata['error'] = str(e)

            await self.save_message(session_id, 'assistant', content, metadata)

            return ChatResponse(
                content=content,
                metadata=metadata,
                cached=False,
                tokens_used=metadata['tokens_used']
            )

        except Exception as e:
            error_message = f"Erro ao buscar lista de documentos: {str(e)}"
            logger.error(f"Error in _handle_list_request: {str(e)}", exc_info=True)
            metadata = self._get_metadata_template(error=True)
            metadata['error'] = str(e)
            await self.save_message(session_id, 'assistant', error_message, metadata)
            return ChatResponse(content=error_message, metadata=metadata, cached=False)

    async def _handle_summary_request(self, session_id: str, query: str) -> ChatResponse:
        """Handle requests for document summaries using LLM for natural response."""
        try:
            summary_data = await self._get_all_documents_summary()

            if not summary_data or summary_data['total_documents'] == 0:
                # Use Gemini for natural response even when no documents
                prompt = f"""O usuário pediu um resumo das categorias dos documentos fiscais, mas não foram encontrados documentos no banco de dados.

Por favor, responda de forma natural explicando que não há documentos disponíveis para análise."""
            else:
                # Prepare raw data for Gemini
                total = summary_data['total_documents']
                total_value = summary_data['total_value']
                categories = summary_data['by_type']
                issuers = summary_data['by_issuer']

                prompt = f"""O usuário pediu um resumo das categorias dos documentos fiscais no sistema.

**Dados brutos do banco de dados:**
- Total de documentos fiscais: {total}
- Valor total dos documentos: R$ {total_value:,.2f}
- Número de categorias diferentes: {len(categories)}
- Número de emissores diferentes: {len(issuers)}

**Distribuição por categoria (dados brutos):**
"""
                for category, count in categories.items():
                    percentage = (count / total) * 100
                    prompt += f"- {category}: {count} documentos ({percentage:.1f}%)\n"

                prompt += f"""

**Principais emissores (dados brutos):**
"""
                sorted_issuers = sorted(issuers.items(), key=lambda x: x[1], reverse=True)
                for issuer, count in sorted_issuers[:5]:
                    prompt += f"- {issuer}: {count} documentos\n"

                prompt += f"""

**Instruções para resposta:**
Responda de forma natural e conversacional, como se estivesse analisando os dados e explicando para o usuário.
Use os dados fornecidos para criar um resumo claro e informativo.
Estruture a resposta de forma organizada, destacando:
1. O total geral de documentos
2. A distribuição por categoria com percentuais
3. Os principais emissores
4. Observações relevantes sobre os dados

Use formatação markdown (negrito, tabelas, listas) para melhorar a legibilidade.
Seja específico e use os números exatos do banco de dados.
Responda em português de forma profissional e útil."""

            # Send to Gemini for natural formatting
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ]

            response = self.model.invoke(messages, config={
                'temperature': 0.2,
                'max_tokens': 1000,
                'top_p': 0.9,
                'frequency_penalty': 0.3,
                'presence_penalty': 0.3
            })

            content = response.content if hasattr(response, 'content') else str(response)
            content = self._clean_response_content(content)

            # Create metadata
            metadata = {
                'model': self.model_name or 'unknown',
                'timestamp': datetime.now().isoformat(),
                'tokens_used': len(content.split()),
                'query_type': 'summary',
                'raw_data': summary_data
            }

            await self.save_message(session_id, 'assistant', content, metadata)

            return ChatResponse(
                content=content,
                metadata=metadata,
                cached=False,
                tokens_used=metadata['tokens_used']
            )

        except Exception as e:
            error_message = f"Erro ao gerar resumo: {str(e)}"
            await self.save_message(session_id, 'assistant', error_message, {'error': True})
            return ChatResponse(content=error_message, metadata={'error': True}, cached=False)

    async def _handle_specific_search(self, session_id: str, query: str, context: Optional[Dict[str, Any]]) -> ChatResponse:
        """Handle specific document searches using RAG when available."""
        document_context = DocumentContext(documents=[], summaries=[], insights=[])

        try:
            # Tentar usar RAG se disponível para busca semântica
            try:
                from backend.services.rag_service import RAGService
                rag_service = RAGService()

                # Gerar embedding da query
                query_embedding = rag_service.embedding_service.generate_query_embedding(query)

                # Buscar documentos relevantes usando RAG
                similar_docs = rag_service.vector_store.get_document_context(
                    query_embedding=query_embedding,
                    max_documents=context.get('limit', 5) if context else 5,
                    max_chunks_per_document=2
                )

                if similar_docs:
                    # Extrair IDs dos documentos
                    doc_ids = [doc['fiscal_document_id'] for doc in similar_docs]

                    # Buscar documentos completos usando PostgreSQL direto
                    from backend.database.postgresql_storage import PostgreSQLStorage
                    db = PostgreSQLStorage()

                    documents = []
                    for doc_id in doc_ids:
                        doc = db.get_fiscal_document(doc_id)
                        if doc:
                            # Adicionar similaridade do RAG
                            doc_similarity = next((d['total_similarity'] for d in similar_docs if d['fiscal_document_id'] == doc_id), 0)
                            doc['rag_similarity'] = doc_similarity
                            documents.append(doc)

                    if documents:
                        document_context = DocumentContext(
                            documents=documents,
                            summaries=[],
                            insights=[]
                        )
                        logger.info(f"RAG search found {len(documents)} relevant documents")

            except Exception as rag_error:
                logger.warning(f"RAG search failed, using fallback: {rag_error}")
                # Fallback para busca por texto
                if context and 'document_types' in context:
                    relevant_docs = await self._search_documents(query, limit=context.get('limit', 5))
                    if relevant_docs:
                        documents = []
                        for doc in relevant_docs:
                            if isinstance(doc, tuple) and len(doc) > 0:
                                doc = doc[0]
                            documents.append(doc)

                        document_context = DocumentContext(
                            documents=documents,
                            summaries=[],
                            insights=[]
                        )

        except Exception as e:
            logger.error(f"Erro na busca específica: {e}")

        # Get conversation history for context
        history_context = await self.get_conversation_context(session_id)

        # Prepare context for LLM
        context_prompt = self._prepare_context_prompt(query, document_context, context, history_context)

        # Generate response using the chat model
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"{context_prompt}\n\nPergunta: {query}")
        ]

        try:
            response = self.model.invoke(messages, config={
                'temperature': 0.3,
                'max_tokens': 1000,
                'top_p': 0.9,
                'frequency_penalty': 0.5,
                'presence_penalty': 0.5
            })

            content = response.content if hasattr(response, 'content') else str(response)
            content = self._clean_response_content(content)

            # Create metadata
            metadata = {
                'model': self.model_name or 'unknown',
                'timestamp': datetime.now().isoformat(),
                'tokens_used': len(content.split()),
                'rag_used': len(document_context.documents) > 0,
                'documents_found': len(document_context.documents)
            }

            # Cache the response
            if context:
                await self.cache.cache_response(
                    query=query,
                    context=context,
                    response=content,
                    metadata=metadata,
                    query_type=context.get('query_type', 'general'),
                    session_id=session_id
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

    def _format_as_table(self, content: str) -> str:
        """Format lists and document information as Markdown tables."""
        try:
            # Check for document types
            doc_keywords = ['nfe', 'nf-e', 'cte', 'ct-e', 'mdfe', 'md-fe', 'nfse', 'nfs-e', 'nfce', 'nfc-e']
            
            # Check for bullet point lists
            lines = content.split('\n')
            bullet_points = [line.strip('-*• ') for line in lines if line.strip().startswith(('- ', '* ', '• '))]
            
            # If we found a list with more than 2 items, format as table
            if len(bullet_points) > 2:
                # Try to split each bullet into columns
                table_rows = []
                for point in bullet_points:
                    # Try to split on common separators
                    parts = re.split(r'[:\-]\s*', point, maxsplit=1)
                    if len(parts) == 2:
                        table_rows.append([parts[0].strip(), parts[1].strip()])
                    else:
                        table_rows.append([point.strip(), ''])
                
                # If we have at least 2 columns, format as table
                if table_rows and len(table_rows[0]) > 1:
                    table = ['| ' + ' | '.join(['Item', 'Descrição']) + ' |',
                             '|' + '|'.join(['---'] * len(table_rows[0])) + '|']
                    for row in table_rows:
                        table.append('| ' + ' | '.join(row) + ' |')
                    return '\n'.join(table)
            
            # Document types table (special case) - improved detection
            has_doc_types = any(keyword in content.lower() for keyword in doc_keywords)
            has_list_indicators = any(indicator in content.lower() for indicator in ['lista de', 'tipos de', 'documentos:', 'categorias:'])
            
            if has_doc_types and has_list_indicators:
                return """
| Documento | Nome Completo | Finalidade Principal |
|-----------|---------------|----------------------|
| **NF-e** | Nota Fiscal Eletrônica | Documentação de operações com mercadorias |
| **NFC-e** | Nota Fiscal de Consumidor Eletrônica | Vendas a consumidores finais |
| **CT-e** | Conhecimento de Transporte Eletrônico | Documentação de serviços de transporte |
| **MDF-e** | Manifesto de Documentos Fiscais | Agrupamento de documentos de transporte |
| **NFSe** | Nota Fiscal de Serviço Eletrônica | Documentação de prestação de serviços |
| **CF-e** | Cupom Fiscal Eletrônico | Documentação de vendas no varejo (alguns estados) |

**Legenda**:
- **NF-e/NFC-e**: Documentos de venda
- **CT-e/MDF-e**: Documentos de transporte
- **NFSe/CF-e**: Documentos de serviço/varejo
"""
            
            # If no special formatting applied, return original content
            return content
            
        except Exception as e:
            logger.warning(f"Error formatting as table: {e}")
            return content

    def _clean_response_content(self, content: str) -> str:
        """Clean and format the LLM response content."""
        if not content:
            return ""

        # Remove extra whitespace and normalize line breaks
        cleaned = content.strip()

        # Fix common formatting issues
        cleaned = cleaned.replace('```json', '```')
        cleaned = cleaned.replace('```python', '```')

        # First, try to format as table if appropriate
        if any(keyword in cleaned.lower() for keyword in ['tabela', 'lista de', 'documentos fiscais', 'exemplo:', 'tipos de']):
            formatted = self._format_as_table(cleaned)
            if formatted != cleaned:  # Only return if formatting was applied
                return formatted
        
        # Split into sentences for better processing
        import re
        sentences = re.split(r'(?<=[.!?])\s+', cleaned)
        
        # Remove duplicate sentences while preserving order
        seen = set()
        clean_sentences = []
        for sentence in sentences:
            # Normalize and check for duplicates
            norm_sent = ' '.join(sentence.lower().split())
            if norm_sent not in seen and len(norm_sent) > 10:  # Ignore very short sentences
                seen.add(norm_sent)
                clean_sentences.append(sentence)
        
        # Join back with proper spacing
        cleaned_content = ' '.join(clean_sentences)
        
        # Remove any remaining repeated phrases (simple heuristic)
        words = cleaned_content.split()
        unique_words = []
        for word in words:
            if len(unique_words) < 2 or word.lower() not in [w.lower() for w in unique_words[-3:]]:
                unique_words.append(word)
        
        return ' '.join(unique_words)

    def _prepare_context_prompt(
            self,
            query: str,
            document_context: DocumentContext,
            context: Optional[Dict[str, Any]],
            history_context: str = ""
    ) -> str:
        """Prepara o contexto para o prompt do LLM.
        
        Args:
            query: A consulta do usuário
            document_context: Contexto dos documentos relevantes
            context: Contexto adicional (filtros, preferências, etc.)
            history_context: Histórico da conversa
            
        Returns:
            str: Contexto formatado para o prompt
        """
        """Prepare context information for the LLM prompt."""
        context_parts = []
        has_documents = bool(document_context and document_context.documents)

        # Add document context if available
        if has_documents:
            context_parts.append("📄 Documentos disponíveis para análise:")
            
            # Tenta formatar como tabela se for uma lista de documentos
            if len(document_context.documents) > 1:
                # Extrai os campos mais importantes para a tabela
                table_header = "| Tipo | Número | Emissor | Data | Valor |\n"
                table_header += "|------|--------|---------|------|-------|\n"
                
                table_rows = []
                for doc in document_context.documents[:5]:  # Limita a 5 documentos na tabela
                    doc_type = doc.get('document_type', 'N/A')
                    doc_number = doc.get('document_number', 'N/A')
                    issuer = doc.get('issuer_name') or doc.get('issuer_cnpj', 'N/A')
                    date = doc.get('emission_date') or doc.get('created_at', 'N/A')
                    
                    # Tenta extrair o valor total dos dados extraídos
                    total_value = 'N/A'
                    if 'extracted_data' in doc and doc['extracted_data']:
                        try:
                            if isinstance(doc['extracted_data'], str):
                                data = json.loads(doc['extracted_data'])
                            else:
                                data = doc['extracted_data']
                                
                            if isinstance(data, dict):
                                total_value = data.get('total', data.get('valor_total', 'N/A'))
                        except (json.JSONDecodeError, AttributeError):
                            pass
                    
                    table_rows.append(f"| {doc_type} | {doc_number} | {issuer} | {date} | {total_value} |")
                
                if table_rows:
                    context_parts.append(table_header + "\n".join(table_rows))
            
            # Se não for uma tabela ou além da tabela, mostra detalhes adicionais
            if len(document_context.documents) == 1 or len(document_context.documents) > 5:
                for doc in document_context.documents[:3]:  # Limita a 3 documentos detalhados
                    doc_info = [
                        f"- {k}: {v}" for k, v in doc.items()
                        if k not in ['content', 'embedding', 'extracted_data'] and v is not None
                    ]
                    if doc_info:
                        context_parts.append("\n".join(doc_info))
                        
                    # Adiciona dados extraídos formatados, se disponíveis
                    if 'extracted_data' in doc and doc['extracted_data']:
                        try:
                            if isinstance(doc['extracted_data'], str):
                                data = json.loads(doc['extracted_data'])
                            else:
                                data = doc['extracted_data']
                                
                            if isinstance(data, dict):
                                extracted_info = [
                                    f"- {k}: {v}" for k, v in data.items()
                                    if v is not None and k not in ['content', 'embedding']
                                ]
                                if extracted_info:
                                    context_parts.append("\nDados extraídos:" + "\n" + "\n".join(extracted_info[:5]))  # Limita a 5 itens
                        except (json.JSONDecodeError, AttributeError):
                            pass
        
        # Add conversation history if available
        if history_context:
            context_parts.append(f"\n💬 Histórico da Conversa:\n{history_context}")

        # Add instructions for response
        if has_documents:
            context_parts.append(
                "\n📝 Instruções para a resposta:\n"
                "1. Analise a pergunta e verifique se ela se refere aos documentos carregados.\n"
                "2. Se a pergunta for sobre os documentos, responda com base neles.\n"
                "3. Se a pergunta for mais geral ou não houver documentos relevantes, use seu conhecimento geral.\n"
                "4. Estruture a resposta de forma clara e objetiva."
            )
        else:
            context_parts.append(
                "\nℹ️ Não há documentos específicos carregados. "
                "Você deve responder com base no seu conhecimento geral sobre documentos fiscais brasileiros.\n"
                "\n📝 Instruções para a resposta:\n"
                "1. Responda de forma clara e completa, mesmo sem documentos específicos.\n"
                "2. Use seu conhecimento sobre legislação fiscal brasileira.\n"
                "3. Se a pergunta for muito específica e exigir documentos, explique isso ao usuário.\n"
                "4. Formate a resposta de forma organizada e fácil de entender."
            )

        # Add insights if available (after instructions to keep them prominent)
        if has_documents and hasattr(document_context, 'insights') and document_context.insights:
            context_parts.append("\n🔍 Insights identificados nos documentos:")
            for insight in document_context.insights[:3]:  # Limit to top 3 insights
                if isinstance(insight, dict):
                    if 'insight_type' in insight and 'insight_text' in insight:
                        context_parts.append(f"📌 {insight['insight_type'].title()}:")
                        context_parts.append(f"   {insight['insight_text']}")
                    elif 'insight_text' in insight:
                        context_parts.append(f"- {insight['insight_text']}")
                elif isinstance(insight, str):
                    context_parts.append(f"- {insight}")

        return "\n".join(context_parts) if context_parts else "Nenhum contexto específico disponível."

