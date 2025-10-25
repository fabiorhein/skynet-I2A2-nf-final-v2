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

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

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
            # Configuração do modelo Gemini 2.0 Flash com LangChain
            try:
                self.model = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    google_api_key=GOOGLE_API_KEY,
                    temperature=0.0,
                    request_timeout=30
                )
                self.model_name = 'gemini-2.0-flash'
                logger.info("✅ Successfully initialized Gemini model: gemini-2.0-flash")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Failed to initialize Gemini model: {error_msg}")
                if "quota" in error_msg.lower() or "429" in error_msg:
                    friendly_msg = (
                        "Parece que excedemos o limite de requisições gratuitas da API do Gemini para hoje.\n\n"
                        "- Limite diário atingido: 200 requisições\n"
                        "- Tempo estimado para liberação: aproximadamente 1 minuto\n"
                        "- Modelo afetado: Gemini 2.0 Flash\n\n"
                        "O que você pode fazer:\n"
                        "1. Aguarde cerca de 1 minuto antes de tentar novamente\n"
                        "2. Se precisar de mais requisições, considere:\n"
                        "   - Verificar seu plano e limites de cota\n"
                        "   - Acessar: https://ai.google.dev/gemini-api/docs/rate-limits"
                    )
                    raise Exception(friendly_msg) from e
                raise

        # Simple conversation history (replaces deprecated LangChain memory)
        self.conversation_history = {}

        # System prompt
        self.system_prompt = """
        Você é um assistente especialista em documentos fiscais brasileiros. Siga estas diretrizes:

        1. Seja conciso e vá direto ao ponto.
        2. Use formatação Markdown para melhorar a legibilidade.
        3. Quando listar documentos fiscais, use tabelas para melhor organização.
        4. Destaque termos técnicos em **negrito**.
        5. Use tópicos e subtópicos para organizar informações complexas.

        **Formatos preferenciais:**
        - Para listas de documentos: use tabelas Markdown
        - Para comparações: use listas com marcadores
        - Para processos passo a passo: use listas numeradas
        - Para destaques: use **negrito** ou *itálico*

        **Exemplo de tabela para documentos fiscais:**
        | Documento | Nome Completo | Finalidade |
        |-----------|---------------|------------|
        | NF-e | Nota Fiscal Eletrônica | Operações com mercadorias |

        **Exemplo de lista para dicas:**
        - Dica 1: Verifique sempre a validade
        - Dica 2: Mantenha os dados atualizados

        Responda sempre em português claro e objetivo.
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

        # Prepare messages for the chat model
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"{context_prompt}\n\nPergunta: {query}")
        ]

        try:
            # Generate response using the chat model with more specific parameters
            response = self.model.invoke(messages, config={
                'temperature': 0.3,  # Reduz a criatividade para respostas mais focadas
                'max_tokens': 1000,  # Limita o tamanho da resposta
                'top_p': 0.9,        # Controla a diversidade das respostas
                'frequency_penalty': 0.5,  # Penaliza repetições
                'presence_penalty': 0.5    # Penaliza tópicos já mencionados
            })
            
            # Extract and clean response content
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Clean up any repeated phrases or words
            content = self._clean_response_content(content)
            
            # Create metadata
            metadata = {
                'model': self.model_name or 'unknown',
                'timestamp': datetime.now().isoformat(),
                'tokens_used': len(content.split())  # Estimativa simples de tokens
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
        """Prepare context information for the LLM prompt."""
        context_parts = []
        has_documents = bool(document_context and document_context.documents)

        # Add document context if available
        if has_documents:
            context_parts.append("📄 Documentos disponíveis para análise:")
            for doc in document_context.documents[:3]:  # Limit to top 3 documents
                doc_info = [
                    f"- {k}: {v}" for k, v in doc.items()
                    if k not in ['content', 'embedding'] and v is not None
                ]
                if doc_info:
                    context_parts.append("\n".join(doc_info))
        
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
