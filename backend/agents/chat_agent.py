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
from datetime import datetime, timedelta, timezone, date, time
from dataclasses import dataclass
import uuid
import logging
import re
from decimal import Decimal

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
from backend.database.storage_manager import storage_manager
from backend.services.rag_service import RAGService
from backend.services.vector_store_service import VectorStoreService


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

            return DocumentContext(
                documents=documents,
                summaries=[],
                insights=[]
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
            try:
                model_name = 'gemini-2.0-flash'
                self.model = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=GOOGLE_API_KEY,
                    temperature=0.0,
                    request_timeout=30
                )
                self.model_name = model_name
                logger.info(f"✅ Successfully initialized Gemini model: {model_name}")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Failed to initialize Gemini models: {error_msg}")
                if "quota" in error_msg.lower() or "429" in error_msg:
                    friendly_msg = (
                        "Limite de quota da API do Gemini excedido."
                    )
                else:
                    friendly_msg = (
                        "Erro ao inicializar modelos Gemini."
                    )
                raise Exception(friendly_msg) from e

        # System prompt
        self.system_prompt = """
        Você é um assistente especialista em documentos fiscais brasileiros, integrado a um sistema híbrido de busca.
        Sua principal função é classificar a pergunta do usuário e, em seguida, usar os dados fornecidos para dar uma resposta precisa.
        NUNCA diga que não tem acesso a informações ou peça para o usuário carregar documentos que já estão no sistema.

        **Seu Processo Interno:**
        1.  **Analisar e Classificar:** Primeiro, você recebe a pergunta e a classifica como `metadata_query` ou `content_query` (RAG).
        2.  **Executar a Ação Correta:**
            *   Para `metadata_query` (perguntas sobre totais, listas, datas, "última nota"), o sistema executará uma consulta SQL direta no banco de dados.
            *   Para `content_query` (perguntas sobre itens, valores específicos dentro de uma nota, análises fiscais), o sistema usará a busca semântica (RAG).
        3.  **Formular a Resposta:** Você receberá os dados brutos (seja de SQL ou RAG) e deve usá-los para formular uma resposta clara, natural e em português.

        **Diretrizes de Resposta:**
        -   **Precisão Absoluta:** Baseie 100% da sua resposta nos dados fornecidos no contexto. Não invente informações.
        -   **Confiança:** Aja como se você mesmo tivesse buscado a informação. Use frases como "A última nota importada foi..." em vez de "Segundo os dados que recebi...".
        -   **Clareza:** Use formatação Markdown (negrito, listas, tabelas) para tornar a informação fácil de ler.

        **Exemplos de Respostas para Perguntas de Metadados:**
        -   **Usuário:** "Qual a última nota que importei?"
            -   **Sua Resposta (após receber dados da query SQL):** "A última nota fiscal importada foi a **NF-e 12345** do fornecedor **Empresa Exemplo Ltda**, no valor de **R$ 1.500,00**, importada em **29/10/2025 às 09:15**."
        -   **Usuário:** "Quantas notas temos de São Paulo?"
            -   **Sua Resposta:** "Atualmente, existem **152 notas fiscais** emitidas por fornecedores de São Paulo no banco de dados."

        **Exemplos de Respostas para Perguntas de Conteúdo (RAG):**
        -   **Usuário:** "Quais os itens da nota fiscal 456?"
            -   **Sua Resposta:** "A NF-e 456 contém os seguintes itens:
                - Item 1: Parafuso Sextavado (100 unidades) - R$ 50,00
                - Item 2: Porca Autotravante (100 unidades) - R$ 35,00"
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

    async def _get_all_documents_summary(self, time_filter: Optional[Union[str, datetime]] = None) -> Dict[str, Any]:
        """
        Obtém um resumo dos documentos para análise de categorias.
        
        Args:
            time_filter: Filtra documentos criados após esta data/hora.
                       Pode ser uma string de linguagem natural (ex: "hoje") ou um objeto datetime.
        """
        parsed_time_filter = None
        if isinstance(time_filter, str):
            parsed_time_filter = self._parse_time_filter(time_filter)
        else:
            parsed_time_filter = time_filter

        return await self.document_analyzer.get_all_documents_summary(time_filter=parsed_time_filter)

    def _detect_validation_query(self, query: str) -> Optional[Dict[str, Any]]:
        """Heuristically detect validation-related queries without invoking the LLM."""

        validation_keywords = [
            'validaç',
            'validac',
            'inconsistência',
            'inconsistencia',
            'status da validação',
            'status de validação',
            'status da validacao',
            'status de validacao'
        ]

        query_lower = query.lower()
        if any(keyword in query_lower for keyword in validation_keywords):
            params: Dict[str, Any] = {}
            reference = self._extract_document_reference(query)
            if reference:
                params['document_reference'] = reference
            return {'intent': 'validation', 'params': params}

        return None

    def _get_query_intent_with_llm(self, query: str) -> Dict[str, Any]:
        """Classify the user's query using an LLM to determine the required action."""
        
        prompt = f"""
        Analise a pergunta do usuário e classifique-a em uma das seguintes categorias. Extraia também os parâmetros relevantes.

        **Categorias:**
        - `count`: Pergunta sobre a quantidade total de documentos.
        - `summary`: Pede um resumo ou distribuição por categoria (tipo, emissor).
        - `list`: Pede uma lista de documentos. Pode incluir filtros como "últimos", "recentes", ou por data.
        - `validation`: Solicita validações, status ou inconsistências de um documento específico.
        - `rag`: Pergunta sobre o conteúdo específico de um ou mais documentos, que exige análise semântica.
        - `generic`: Conversa geral, saudação ou pergunta que não se encaixa nas outras categorias.

        **Extração de Parâmetros:**
        - `limit` (inteiro): Se o usuário especificar um número (ex: "5 últimas notas").
        - `time_filter` (string): Se houver um filtro de tempo (ex: "hoje", "últimos 7 dias").
        - `order_by` (string): Se a ordenação for clara (ex: "maior valor", "mais recente").
        - `document_reference` (string): Identificador do documento (ex: chave, número, nome do arquivo).

        **Exemplos:**
        1. Pergunta: "quantas notas nós temos?"
           Resposta: {{"intent": "count", "params": {{}}}}
        2. Pergunta: "me mostre a última nota importada"
           Resposta: {{"intent": "list", "params": {{"limit": 1, "order_by": "created_at"}}}}
        3. Pergunta: "quais os itens da nota fiscal do fornecedor X?"
           Resposta: {{"intent": "rag", "params": {{"vendor": "X"}}}}
        4. Pergunta: "pode me trazer as validações da NF-e 123?"
           Resposta: {{"intent": "validation", "params": {{"document_reference": "NF-e 123"}}}}
        5. Pergunta: "Olá, tudo bem?"
           Resposta: {{"intent": "generic", "params": {{}}}}
        6. Pergunta: "faça um resumo por tipo de documento"
           Resposta: {{"intent": "summary", "params": {{}}}}

        **Pergunta do Usuário:** "{query}"

        **Sua Resposta (APENAS o JSON):**
        """
        
        try:
            messages = [HumanMessage(content=prompt)]
            response = self.model.invoke(messages, config={'temperature': 0.0})
            content = response.content if hasattr(response, 'content') else str(response)
            
            json_response_str = content.strip().replace('`', '').replace('json', '')
            result = json.loads(json_response_str)
            
            if 'intent' in result and 'params' in result:
                return result
            else:
                return {'intent': 'rag', 'params': {'query': query}} # Fallback
                
        except Exception as e:
            logger.error(f"Error classifying intent with LLM: {e}")
            return {'intent': 'rag', 'params': {'query': query}} # Fallback on error

    def _clean_response_content(self, content: str) -> str:
        # Simple cleaning for now
        return content.strip()

    async def generate_response(
        self,
        session_id: str,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ChatResponse:
        """Generate a response using LLM with caching and context."""

        if not self.model:
            error_message = "API do Google Gemini não configurada."
            await self.save_message(session_id, 'assistant', error_message, {'error': True})
            return ChatResponse(
                content=error_message,
                metadata={'error': True, 'error_type': 'missing_api_key'},
                cached=False
            )

        try:
            # Heuristic detection for validation queries before LLM call
            heuristic_intent = self._detect_validation_query(query)
            if heuristic_intent:
                intent_data = heuristic_intent
            else:
                intent_data = self._get_query_intent_with_llm(query)
            intent = intent_data.get('intent', 'rag')
            params = intent_data.get('params', {})

            if intent == 'count':
                return await self._handle_count_request(session_id, query, params)
            elif intent == 'summary':
                return await self._handle_summary_request(session_id, query, params)
            elif intent == 'list':
                return await self._handle_list_request(session_id, query, params)
            elif intent == 'validation':
                return await self._handle_validation_request(session_id, query, params)
            else: # Handles 'rag' and 'generic'
                return await self._handle_specific_search(session_id, query, context)

        except Exception as e:
            logger.error(f"Erro ao processar pergunta: {e}", exc_info=True)
            return await self._handle_specific_search(session_id, query, context)

    async def _handle_count_request(self, session_id: str, query: str, params: Dict[str, Any]) -> ChatResponse:
        """Handle requests for document counts using LLM for natural response."""
        try:
            summary_data = await self._get_all_documents_summary()

            if not summary_data or summary_data['total_documents'] == 0:
                prompt = "O usuário perguntou sobre a quantidade de documentos, mas não há nenhum no sistema. Informe que não há documentos carregados."
            else:
                total = summary_data['total_documents']
                total_value = summary_data['total_value']
                categories = summary_data['by_type']
                
                prompt = f"""
                O usuário perguntou sobre a quantidade de documentos. Responda de forma natural usando os seguintes dados:
                - Total de documentos: {total}
                - Valor total: R$ {total_value:,.2f}
                - Categorias: {json.dumps(categories)}
                """

            messages = await self._build_llm_messages(session_id, prompt)
            response = self.model.invoke(messages)
            content = self._clean_response_content(response.content)
            
            metadata = { 'query_type': 'count', 'raw_data': summary_data }
            await self.save_message(session_id, 'assistant', content, metadata)

            return ChatResponse(content=content, metadata=metadata)

        except Exception as e:
            error_message = f"Erro ao buscar contagem de documentos: {str(e)}"
            await self.save_message(session_id, 'assistant', error_message, {'error': True})
            return ChatResponse(content=error_message, metadata={'error': True})

    async def _build_llm_messages(self, session_id: str, prompt: str) -> List[Union[SystemMessage, HumanMessage]]:
        """Build the list of messages for the LLM, including conversation history."""
        conversation_context = await self.get_conversation_context(session_id)
        
        full_prompt = f"""**Histórico da Conversa Anterior:**
{conversation_context}

**Dados para a Pergunta Atual:**
{prompt}"""

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=full_prompt)
        ]

    def _parse_time_filter(self, time_filter_str: Optional[str]) -> Optional[datetime]:
        """Parse a natural language time filter string into a datetime object."""
        if not time_filter_str:
            return None

        now = datetime.now()
        filter_lower = time_filter_str.lower()

        if 'hoje' in filter_lower:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if 'ontem' in filter_lower:
            return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        match = re.search(r'últimos (\d+) dias', filter_lower)
        if match:
            days = int(match.group(1))
            return now - timedelta(days=days)

        return None

    def _get_metadata_template(self, is_recent_query: bool = False, error: bool = False) -> Dict[str, Any]:
        """Return a standardized metadata template."""
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

    def _build_metadata_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare a sanitized list of documents to store in message metadata."""

        metadata_documents: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()

        for doc in documents:
            if not isinstance(doc, dict):
                continue

            doc_id = doc.get('id')
            full_doc: Optional[Dict[str, Any]] = None

            if doc_id and doc_id not in seen_ids:
                try:
                    full_doc = self.storage.get_fiscal_document(doc_id)
                except Exception as fetch_error:
                    logger.debug(f"Não foi possível carregar documento completo {doc_id}: {fetch_error}")

            selected_doc = full_doc or doc
            metadata_doc = self._prepare_document_metadata(selected_doc if isinstance(selected_doc, dict) else {})

            if metadata_doc:
                metadata_documents.append(metadata_doc)
                doc_identifier = metadata_doc.get('id')
                if isinstance(doc_identifier, str):
                    seen_ids.add(doc_identifier)

        return metadata_documents

    def _prepare_document_metadata(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Sanitize document data before storing in metadata."""

        if not document:
            return None

        issuer_cnpj = document.get('issuer_cnpj')
        issuer_name = document.get('issuer_name')

        extracted = document.get('extracted_data')
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except (TypeError, ValueError):
                extracted = {}

        if isinstance(extracted, dict):
            issuer_data = extracted.get('emitente') or {}
            issuer_cnpj = issuer_cnpj or issuer_data.get('cnpj')
            issuer_name = issuer_name or issuer_data.get('razao_social') or issuer_data.get('nome')

        metadata_doc = {
            'id': document.get('id'),
            'file_name': document.get('file_name'),
            'document_number': document.get('document_number'),
            'document_key': document.get('document_key'),
            'document_type': document.get('document_type'),
            'issuer_cnpj': issuer_cnpj,
            'issuer_name': issuer_name,
            'validation_status': document.get('validation_status'),
            'created_at': document.get('created_at')
        }

        sanitized = {
            key: self._sanitize_metadata_value(value)
            for key, value in metadata_doc.items()
            if value not in (None, '', [])
        }

        return sanitized or None

    def _sanitize_metadata_value(self, value: Any) -> Any:
        """Ensure metadata values are JSON serializable."""

        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (bytes, bytearray)):
            return value.decode('utf-8', errors='ignore')
        return value

    async def _get_recent_documents_from_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Return the most recent assistant documents metadata from conversation history."""

        history = await self.get_conversation_history(session_id)

        for message in reversed(history):
            if not isinstance(message, dict):
                continue
            if message.get('message_type') != 'assistant':
                continue

            metadata = message.get('metadata') or {}
            documents = metadata.get('documents') if isinstance(metadata, dict) else []

            if isinstance(documents, list) and documents:
                return [doc for doc in documents if isinstance(doc, dict)]

        return []

    def _find_documents_by_reference(self, reference: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search storage for documents matching a textual reference."""

        if not reference:
            return []

        try:
            search_page = self.storage.get_fiscal_documents(page=1, page_size=100)
            documents = getattr(search_page, 'items', [])
        except Exception as e:
            logger.error(f"Erro ao buscar documentos por referência: {e}")
            return []

        matched = [doc for doc in documents if isinstance(doc, dict) and self._matches_reference(doc, reference)]

        return self._load_full_documents(matched, limit)

    def _load_full_documents(self, documents: List[Dict[str, Any]], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Ensure we have full document data for the provided entries."""

        results: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()

        for doc in documents:
            if not isinstance(doc, dict):
                continue

            doc_id = doc.get('id')
            if doc_id and doc_id in seen_ids:
                continue

            full_doc = None
            if doc_id:
                try:
                    full_doc = self.storage.get_fiscal_document(doc_id)
                except Exception as fetch_error:
                    logger.debug(f"Não foi possível carregar documento completo {doc_id}: {fetch_error}")

            selected_doc = full_doc or doc

            if isinstance(selected_doc, dict):
                results.append(selected_doc)
                if doc_id:
                    seen_ids.add(doc_id)
            if limit and len(results) >= limit:
                break

        return results

    async def _handle_list_request(self, session_id: str, query: str, params: Dict[str, Any]) -> ChatResponse:
        """Handle requests for document lists using LLM for natural response."""
        try:
            query_lower = query.lower()

            doc_limit = params.get('limit')
            order_by = params.get('order_by', 'created_at')
            time_filter_str = params.get('time_filter')
            time_filter = self._parse_time_filter(time_filter_str)

            is_recent_query = (order_by == 'created_at') or (time_filter is not None)
            
            summary_data = await self._get_all_documents_summary(time_filter=time_filter)
            
            if not summary_data or summary_data['total_documents'] == 0:
                message = "📭 Não foram encontrados documentos no sistema com os critérios fornecidos."
                metadata = self._get_metadata_template(is_recent_query=is_recent_query)
                await self.save_message(session_id, 'assistant', message, metadata)
                return ChatResponse(content=message, metadata=metadata)

            total = summary_data['total_documents']
            documents = summary_data['documents']
            
            documents_sorted = documents # The summary already returns them sorted
            
            limit = doc_limit if (doc_limit and doc_limit > 0) else 10
            documents_to_show = documents_sorted[:limit]

            base_prompt = ["O usuário pediu uma lista de documentos. Use os dados abaixo para formular a resposta."]
            base_prompt.append(f"Dados: {json.dumps(documents_to_show, indent=2, default=str)}")
            prompt = "\n".join(base_prompt)

            messages = await self._build_llm_messages(session_id, prompt)
            response = self.model.invoke(messages)
            content = self._clean_response_content(response.content)

            metadata_documents = self._build_metadata_documents(documents_to_show)
            metadata = {
                'query_type': 'list',
                'document_count': len(metadata_documents),
                'total_documents': total,
                'documents': metadata_documents
            }
            await self.save_message(session_id, 'assistant', content, metadata)

            return ChatResponse(content=content, metadata=metadata)

        except Exception as e:
            error_message = f"Erro ao buscar lista de documentos: {str(e)}"
            logger.error(f"Error in _handle_list_request: {str(e)}", exc_info=True)
            metadata = self._get_metadata_template(error=True)
            await self.save_message(session_id, 'assistant', error_message, metadata)
            return ChatResponse(content=error_message, metadata=metadata)

    async def _handle_summary_request(self, session_id: str, query: str, params: Dict[str, Any]) -> ChatResponse:
        """Handle requests for document summaries using LLM for natural response."""
        try:
            summary_data = await self._get_all_documents_summary()

            if not summary_data or summary_data['total_documents'] == 0:
                prompt = "O usuário pediu um resumo, mas não há documentos. Informe que não há dados para analisar."
            else:
                prompt = f"O usuário pediu um resumo dos documentos. Use os seguintes dados para criar um resumo em português:\n{json.dumps(summary_data, indent=2, default=str)}"

            messages = await self._build_llm_messages(session_id, prompt)
            response = self.model.invoke(messages)
            content = self._clean_response_content(response.content)

            metadata = { 'query_type': 'summary', 'raw_data': summary_data }
            await self.save_message(session_id, 'assistant', content, metadata)

            return ChatResponse(content=content, metadata=metadata)

        except Exception as e:
            error_message = f"Erro ao gerar resumo: {str(e)}"
            await self.save_message(session_id, 'assistant', error_message, {'error': True})
            return ChatResponse(content=error_message, metadata={'error': True})

    async def _handle_specific_search(self, session_id: str, query: str, context: Optional[Dict[str, Any]]) -> ChatResponse:
        """Handle specific document searches using RAG."""
        try:
            vector_store = VectorStoreService()
            rag_service = RAGService(vector_store=vector_store)
            
            context_data = await rag_service.get_context_with_metadata(query)
            context_prompt = context_data.get('context')

            if not context_prompt or context_data.get('status') == 'no_matches':
                message = "Não encontrei informações relevantes para sua pergunta."
                metadata = {
                    'query_type': 'rag',
                    'status': context_data.get('status', 'no_context'),
                    'documents': [],
                    'document_count': 0
                }
                await self.save_message(session_id, 'assistant', message, metadata)
                return ChatResponse(content=message, metadata=metadata)

            metadata_documents = self._build_metadata_from_context_docs(context_data.get('documents', []))

            messages = await self._build_llm_messages(session_id, f"{context_prompt}\n\nPergunta: {query}")
            response = self.model.invoke(messages)
            content = self._clean_response_content(response.content)

            metadata = {
                'query_type': 'rag',
                'status': context_data.get('status', 'success'),
                'document_count': len(metadata_documents),
                'documents': metadata_documents
            }
            await self.save_message(session_id, 'assistant', content, metadata)
            
            return ChatResponse(content=content, metadata=metadata)
        
        except Exception as e:
            logger.error(f"RAG search failed, using fallback: {e}", exc_info=True)
            # Fallback to a generic response without RAG
            prompt = "Não consegui realizar a busca semântica. Responda à pergunta do usuário da melhor forma possível sem dados adicionais."
            messages = await self._build_llm_messages(session_id, f"{prompt}\n\nPergunta: {query}")
            response = self.model.invoke(messages)
            content = self._clean_response_content(response.content)
            
            metadata = {
                'query_type': 'rag_fallback',
                'error': str(e)
            }
            await self.save_message(session_id, 'assistant', content, metadata)
            
            return ChatResponse(content=content, metadata=metadata)

    def _build_metadata_from_context_docs(self, context_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert RAG context documents into stored metadata format."""

        if not context_docs:
            return []

        docs_with_id = [
            {'id': doc_id}
            for doc_id in {
                doc.get('fiscal_document_id') or doc.get('id')
                for doc in context_docs
                if doc.get('fiscal_document_id') or doc.get('id')
            }
        ]

        metadata_documents: List[Dict[str, Any]] = []

        if docs_with_id:
            full_docs = self._load_full_documents(docs_with_id, limit=len(docs_with_id))
            metadata_documents = self._build_metadata_documents(full_docs)

        if metadata_documents:
            return metadata_documents

        fallback_metadata = []
        for doc in context_docs:
            entry = {
                'id': doc.get('fiscal_document_id') or doc.get('id'),
                'file_name': doc.get('file_name'),
                'issuer_cnpj': doc.get('issuer_cnpj'),
                'document_number': doc.get('document_number'),
                'document_type': doc.get('document_type')
            }

            sanitized = {
                key: self._sanitize_metadata_value(value)
                for key, value in entry.items()
                if value not in (None, '', [])
            }

            if sanitized:
                fallback_metadata.append(sanitized)

        return fallback_metadata

    async def _handle_validation_request(self, session_id: str, query: str, params: Dict[str, Any]) -> ChatResponse:
        """Handle validation detail requests directly from metadata storage."""

        document_reference = params.get('document_reference', '') or ''
        query_lower = query.lower()
        metadata_docs: List[Dict[str, Any]] = []
        cnpj_tokens = self._extract_cnpjs(query)
        document_type_hints = self._extract_document_type_hints(query_lower)

        try:
            # Attempt to extract potential document reference from query if not provided
            if not document_reference:
                document_reference = self._extract_document_reference(query) or ''

            document_reference = document_reference.strip().strip(' .,;:\n\t')

            if document_reference:
                normalized_ref = document_reference.lower()
                generic_phrases = [
                    'ultima mensagem respondida',
                    'última mensagem respondida',
                    'ultima resposta',
                    'última resposta',
                    'mensagem anterior'
                ]
                if any(phrase in normalized_ref for phrase in generic_phrases):
                    document_reference = ''

            matched_documents: Dict[str, Dict[str, Any]] = {}

            def add_matched(documents: List[Dict[str, Any]]) -> None:
                for doc in documents:
                    if not isinstance(doc, dict):
                        continue
                    doc_id = doc.get('id')
                    key = doc_id or f"generated-{len(matched_documents)}"
                    if key not in matched_documents:
                        matched_documents[key] = doc

            if document_reference:
                add_matched(self._find_documents_by_reference(document_reference))

            for cnpj in cnpj_tokens:
                add_matched(self._find_documents_by_reference(cnpj))

            if not matched_documents:
                metadata_docs = await self._get_recent_documents_from_history(session_id)

                def metadata_matches(doc: Dict[str, Any]) -> bool:
                    if not isinstance(doc, dict):
                        return False

                    if document_reference and not self._matches_reference(doc, document_reference):
                        return False

                    if cnpj_tokens:
                        doc_cnpj = self._normalize_digits(doc.get('issuer_cnpj'))
                        if not doc_cnpj or all(doc_cnpj != token for token in cnpj_tokens):
                            return False

                    if document_type_hints:
                        doc_type = (doc.get('document_type') or '').lower().replace('-', '').replace('_', '')
                        if not doc_type or all(hint not in doc_type for hint in document_type_hints):
                            return False

                    return True

                filtered_metadata = [doc for doc in metadata_docs if metadata_matches(doc)] if metadata_docs else []

                candidate_ids: List[str] = [doc.get('id') for doc in filtered_metadata if isinstance(doc, dict) and doc.get('id')]

                if not candidate_ids and metadata_docs:
                    if document_reference:
                        candidate_ids = [
                            doc.get('id')
                            for doc in metadata_docs
                            if isinstance(doc, dict) and doc.get('id') and self._matches_reference(doc, document_reference)
                        ]

                    if not candidate_ids and cnpj_tokens:
                        candidate_ids = [
                            doc.get('id')
                            for doc in metadata_docs
                            if isinstance(doc, dict) and doc.get('id') and self._normalize_digits(doc.get('issuer_cnpj')) in cnpj_tokens
                        ]

                    if not candidate_ids and document_type_hints:
                        candidate_ids = [
                            doc.get('id')
                            for doc in metadata_docs
                            if isinstance(doc, dict) and doc.get('id') and any(
                                hint in (doc.get('document_type') or '').lower().replace('-', '').replace('_', '')
                                for hint in document_type_hints
                            )
                        ]

                candidate_ids = [doc_id for doc_id in candidate_ids if doc_id]

                if candidate_ids:
                    add_matched(
                        self._load_full_documents(
                            [{'id': doc_id} for doc_id in candidate_ids],
                            limit=len(candidate_ids)
                        )
                    )
                elif not document_reference and metadata_docs:
                    first_doc_id = next((doc.get('id') for doc in metadata_docs if isinstance(doc, dict) and doc.get('id')), None)
                    if first_doc_id:
                        add_matched(
                            self._load_full_documents([
                                {'id': first_doc_id}
                            ], limit=1)
                        )

            matched = [doc for doc in matched_documents.values() if isinstance(doc, dict)]

            if not matched:
                message = (
                    f"❗️ Não encontrei documentos que correspondam a '{document_reference or 'sua descrição'}'.\n"
                    "Verifique se o identificador está correto (nome do arquivo, número ou chave de acesso)."
                )
                metadata = {
                    'query_type': 'validation',
                    'document_reference': document_reference,
                    'matches': 0
                }
                if metadata_docs:
                    metadata['suggestions'] = metadata_docs[:3]
                await self.save_message(session_id, 'assistant', message, metadata)
                return ChatResponse(content=message, metadata=metadata)

            responses = []
            metadata_entries = []

            for doc in matched:
                validations = doc.get('validation_details')
                status = doc.get('validation_status', 'não informado')

                formatted = self._format_validation_details(doc, status, validations)
                responses.append(formatted)

                metadata_entries.append({
                    'document_id': doc.get('id'),
                    'file_name': doc.get('file_name'),
                    'validation_status': status,
                    'has_details': bool(validations),
                    'document_type': doc.get('document_type')
                })

            combined_response = "\n\n".join(responses)
            metadata = {
                'query_type': 'validation',
                'document_reference': document_reference,
                'documents_found': len(matched),
                'documents': metadata_entries
            }

            await self.save_message(session_id, 'assistant', combined_response, metadata)

            return ChatResponse(content=combined_response, metadata=metadata)

        except Exception as e:
            logger.error(f"Erro ao buscar validações: {e}", exc_info=True)
            error_message = "❌ Ocorreu um erro ao buscar as validações. Tente novamente mais tarde."
            metadata = {'query_type': 'validation', 'error': str(e)}
            await self.save_message(session_id, 'assistant', error_message, metadata)
            return ChatResponse(content=error_message, metadata=metadata, cached=False)

    def _normalize_digits(self, value: Optional[str]) -> str:
        if not value:
            return ''
        return re.sub(r'\D', '', str(value))

    def _extract_cnpjs(self, text: str) -> List[str]:
        if not text:
            return []

        found = re.findall(r'\d{14}', text)
        unique: List[str] = []
        for item in found:
            normalized = self._normalize_digits(item)
            if normalized and normalized not in unique:
                unique.append(normalized)
        return unique

    def _extract_document_type_hints(self, text_lower: str) -> List[str]:
        if not text_lower:
            return []

        type_map = {
            'cte': ['cte', 'ct-e'],
            'nfe': ['nfe', 'nf-e', 'nota fiscal eletrônica', 'nota fiscal eletronica'],
            'nfce': ['nfce', 'nfc-e'],
            'mdfe': ['mdfe', 'mdf-e'],
            'nfse': ['nfse', 'nfs-e']
        }

        hints: set[str] = set()
        for key, markers in type_map.items():
            if any(marker in text_lower for marker in markers):
                hints.add(key)

        return list(hints)

    def _matches_reference(self, document: Dict[str, Any], reference: str) -> bool:
        """Check whether a document matches the reference string."""
        if not reference:
            return False

        reference_lower = reference.lower().strip()
        reference_digits = re.sub(r'\D', '', reference_lower)

        fields: List[str] = []

        def add_field(value: Any) -> None:
            if value not in (None, '', []):
                fields.append(str(value))

        add_field(document.get('file_name'))
        add_field(document.get('document_number'))
        add_field(document.get('document_key'))
        add_field(document.get('id'))
        add_field(document.get('issuer_cnpj'))
        add_field(document.get('issuer_name'))

        extracted = document.get('extracted_data')
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except (TypeError, ValueError):
                extracted = {}

        if isinstance(extracted, dict):
            emitente = extracted.get('emitente') or {}
            destinatario = extracted.get('destinatario') or {}

            add_field(emitente.get('cnpj'))
            add_field(emitente.get('razao_social'))
            add_field(emitente.get('nome'))
            add_field(destinatario.get('cnpj'))
            add_field(destinatario.get('razao_social'))
            add_field(destinatario.get('nome'))

        for field in fields:
            field_lower = field.lower()
            if reference_lower and reference_lower in field_lower:
                return True

            if reference_digits:
                field_digits = re.sub(r'\D', '', field_lower)
                if field_digits and reference_digits in field_digits:
                    return True

        return False

    def _format_validation_details(self, document: Dict[str, Any], status: str, validations: Any) -> str:
        """Format validation details into a human-friendly Markdown response."""
        file_name = document.get('file_name', 'Documento sem nome')
        status_icon = {
            'valid': '✅',
            'warning': '⚠️',
            'invalid': '❌'
        }.get(status, 'ℹ️')

        lines = [
            f"**Documento:** {file_name}",
            f"**Status das validações:** {status_icon} {status.capitalize()}"
        ]

        if validations:
            try:
                if isinstance(validations, str):
                    validations = json.loads(validations)

                if isinstance(validations, dict):
                    items = validations.get('items') or validations.get('checks') or []
                    if items:
                        lines.append("\n**Detalhes:**")
                        for item in items:
                            if isinstance(item, dict):
                                title = item.get('title') or item.get('description') or 'Validação'
                                result = item.get('result', 'Sem resultado')
                                detail = item.get('detail') or item.get('message')
                                lines.append(f"- **{title}:** {result}")
                                if detail:
                                    lines.append(f"  - {detail}")
                            else:
                                lines.append(f"- {item}")
                    else:
                        lines.append("\nNenhum detalhe adicional de validação está disponível.")
                else:
                    lines.append("\nValidações registradas em formato não estruturado.")

            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Erro ao interpretar validation_details: {e}")
                lines.append("\nNão foi possível interpretar os detalhes de validação armazenados.")
        else:
            lines.append("\nNenhum detalhe de validação foi registrado para este documento.")

        return "\n".join(lines)