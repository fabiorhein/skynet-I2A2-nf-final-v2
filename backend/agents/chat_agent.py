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
from datetime import datetime, timedelta
from dataclasses import dataclass
import uuid
import logging
import re

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import GOOGLE_API_KEY, SUPABASE_URL, SUPABASE_KEY
from backend.services.document_analyzer import DocumentAnalyzer

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
            # Busca simples mas eficiente usando a API do Supabase
            # Primeiro busca em extracted_data (JSON)
            result1 = self.supabase.table('fiscal_documents').select(
                'id, file_name, document_type, document_number, issuer_cnpj, extracted_data, classification'
            ).or_(
                f'extracted_data.ilike.%{query}%,file_name.ilike.%{query}%,document_type.ilike.%{query}%'
            ).limit(limit).execute()

            # Busca também em document_summaries se existirem
            try:
                result2 = self.supabase.table('document_summaries').select(
                    'fiscal_document_id, summary_text, key_insights'
                ).ilike('summary_text', f'%{query}%').execute()

                # Busca em analysis_insights se existirem
                result3 = self.supabase.table('analysis_insights').select(
                    'fiscal_document_id, insight_text, insight_type, confidence_score'
                ).ilike('insight_text', f'%{query}%').execute()

                # Combina os resultados
                all_docs = {}
                if result1.data:
                    for doc in result1.data:
                        all_docs[doc['id']] = doc

                # Adiciona documentos encontrados através de summaries
                if result2.data:
                    for summary in result2.data:
                        doc_id = summary['fiscal_document_id']
                        if doc_id not in all_docs:
                            # Busca o documento completo
                            doc_result = self.supabase.table('fiscal_documents').select(
                                'id, file_name, document_type, document_number, issuer_cnpj, extracted_data, classification'
                            ).eq('id', doc_id).execute()
                            if doc_result.data:
                                all_docs[doc_id] = doc_result.data[0]

                # Adiciona documentos encontrados através de insights
                if result3.data:
                    for insight in result3.data:
                        doc_id = insight['fiscal_document_id']
                        if doc_id not in all_docs:
                            # Busca o documento completo
                            doc_result = self.supabase.table('fiscal_documents').select(
                                'id, file_name, document_type, document_number, issuer_cnpj, extracted_data, classification'
                            ).eq('id', doc_id).execute()
                            if doc_result.data:
                                all_docs[doc_id] = doc_result.data[0]

                documents = list(all_docs.values())[:limit]

            except Exception as e:
                logger.warning(f"Error in advanced search: {e}")
                documents = result1.data if result1.data else []

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
        self.document_analyzer = DocumentAnalyzer(supabase_client)

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

    async def _get_document_summary(self, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Obtém um resumo dos documentos com base nos filtros fornecidos."""
        return await self.document_analyzer.get_documents_summary(filters)

    async def _get_all_documents_summary(self) -> Dict[str, Any]:
        """Obtém um resumo de TODOS os documentos para análise de categorias."""
        return await self.document_analyzer.get_all_documents_summary()

    def _is_summary_request(self, query: str) -> bool:
        """Verifica se a pergunta é sobre resumo/categorias de documentos."""
        query_lower = query.lower()
        summary_keywords = [
            'resumo', 'sumário', 'categoria', 'tipos de', 'categorias',
            'resumir', 'distribuição', 'mostrar categorias', 'categorias dos documentos'
        ]

        # Não é resumo se for claramente sobre contagem total ou lista
        count_keywords = ['quantidade total', 'quantos documentos', 'total de', 'contagem']
        list_keywords = ['lista', 'listar', 'todos os documentos', 'todas as notas', 'me traga uma lista']

        has_summary = any(keyword in query_lower for keyword in summary_keywords)
        has_count = any(keyword in query_lower for keyword in count_keywords)
        has_list = any(keyword in query_lower for keyword in list_keywords)

        return has_summary and not has_count and not has_list

    def _is_list_request(self, query: str) -> bool:
        """Verifica se a pergunta é sobre lista específica de documentos."""
        query_lower = query.lower()
        list_keywords = [
            'lista', 'listar', 'todos os documentos', 'todas as notas',
            'me traga uma lista', 'mostrar todos', 'exibir todos',
            'documentos fiscais que foram inseridas',
            'notas que foram cadastradas', 'inseridas no banco',
            'com cnpj', 'com valor', 'com descrição'
        ]

        return any(keyword in query_lower for keyword in list_keywords)

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

    async def _handle_list_request(self, session_id: str, query: str) -> ChatResponse:
        """Handle requests for document lists using LLM for natural response."""
        try:
            summary_data = await self._get_all_documents_summary()

            if not summary_data or summary_data['total_documents'] == 0:
                # Use Gemini for natural response even when no documents
                prompt = f"""O usuário pediu uma lista de documentos fiscais, mas não foram encontrados documentos no banco de dados.

Por favor, responda de forma natural explicando que não há documentos disponíveis no sistema."""
            else:
                # Prepare raw data for Gemini
                total = summary_data['total_documents']
                documents = summary_data['documents']

                prompt = f"""O usuário pediu uma lista com todos os documentos fiscais do banco de dados.

**Dados brutos encontrados:**
- Total de documentos: {total}
- Valor total: R$ {summary_data['total_value']:,.2f}

**Lista de documentos (primeiros 15 para não sobrecarregar):**
"""

                # Limit to first 15 documents to avoid token limits
                for i, doc in enumerate(documents[:15], 1):
                    doc_type = doc.get('categorized_type', 'N/A')
                    file_name = doc.get('file_name', 'N/A')
                    cnpj = doc.get('issuer_cnpj', 'N/A')
                    created_at = doc.get('created_at', 'N/A')[:10] if doc.get('created_at') else 'N/A'

                    # Extract value
                    value = 'N/A'
                    if doc.get('extracted_data'):
                        try:
                            data = doc['extracted_data']
                            if isinstance(data, str):
                                import json
                                data = json.loads(data)
                            if isinstance(data, dict):
                                value = data.get('total', data.get('valor_total', data.get('value', 'N/A')))
                        except:
                            value = 'N/A'

                    prompt += f"{i}. **{doc_type}** - {file_name}\n"
                    prompt += f"   CNPJ: {cnpj} | Valor: R$ {value} | Data: {created_at}\n\n"

                if total > 15:
                    prompt += f"*(Mostrando apenas os primeiros 15 documentos. Total no banco: {total})*\n\n"

                prompt += f"""
**Instruções:**
Responda de forma natural e conversacional, como se estivesse apresentando os documentos para o usuário.
Use os dados fornecidos para criar uma lista clara e organizada.
Inclua informações importantes como tipo, emissor, valor e data.
Use formatação markdown para melhorar a legibilidade (tabelas, negrito, etc.).
Seja específico sobre quantos documentos foram encontrados.
Responda em português."""

            # Send to Gemini for natural formatting
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ]

            response = self.model.invoke(messages, config={
                'temperature': 0.2,
                'max_tokens': 1500,
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
                'query_type': 'list',
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
            error_message = f"Erro ao buscar lista de documentos: {str(e)}"
            await self.save_message(session_id, 'assistant', error_message, {'error': True})
            return ChatResponse(content=error_message, metadata={'error': True}, cached=False)

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

                    # Buscar documentos completos
                    result = self.supabase.table('fiscal_documents').select('*').in_('id', doc_ids).execute()

                    if result.data:
                        documents = []
                        for doc in result.data:
                            # Adicionar similaridade do RAG
                            doc_similarity = next((d['total_similarity'] for d in similar_docs if d['fiscal_document_id'] == doc['id']), 0)
                            doc['rag_similarity'] = doc_similarity
                            documents.append(doc)

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
            
            # Document types table (special case)
            if any(keyword in content.lower() for keyword in doc_keywords):
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
        """Clean up response content to remove repetitions and improve quality."""
        # First, try to format as table if appropriate
        if any(keyword in content.lower() for keyword in ['tabela', 'lista de', 'documentos fiscais', 'exemplo:', 'tipos de']):
            formatted = self._format_as_table(content)
            if formatted != content:  # Only return if formatting was applied
                return formatted
            
        # Split into sentences for better processing
        import re
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
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
