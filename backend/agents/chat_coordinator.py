"""
Chat Coordinator - Main interface for the chat system.

This module provides a high-level interface for the chat functionality,
integrating all the chat components and providing a simple API for the frontend.
"""
import asyncio
from typing import Dict, Any, List, Optional
import logging

from backend.agents.chat_agent import ChatAgent, ChatResponse
from backend.tools.chat_tools import DocumentAnalysisTool, CSVAnalysisTool, InsightGenerator

logger = logging.getLogger(__name__)


class ChatCoordinator:
    """Main coordinator for chat system."""

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.chat_agent = ChatAgent(supabase_client)
        self.document_tool = DocumentAnalysisTool(supabase_client)
        self.csv_tool = CSVAnalysisTool(supabase_client)
        self.insight_generator = InsightGenerator(self.document_tool, self.csv_tool)

    async def initialize_session(self, session_name: str = None) -> str:
        """Initialize a new chat session."""
        return await self.chat_agent.create_session(session_name)

    async def process_query(
        self,
        session_id: str,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a user query and return response."""

        try:
            # Save user message
            await self.chat_agent.save_message(session_id, 'user', query)

            # Determine query type and prepare context
            enhanced_context = await self._enhance_context(query, context)

            # Generate response
            response = await self.chat_agent.generate_response(
                session_id=session_id,
                query=query,
                context=enhanced_context
            )

            return {
                'success': True,
                'response': response.content,
                'metadata': response.metadata,
                'cached': response.cached,
                'tokens_used': response.tokens_used
            }

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'success': False,
                'error': str(e),
                'response': 'Desculpe, ocorreu um erro ao processar sua pergunta.',
                'metadata': {'error': True}
            }

    async def _enhance_context(
        self,
        query: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Enhance context based on query content."""

        enhanced_context = context or {}
        query_lower = query.lower()

        # Detect query type based on keywords
        if any(word in query_lower for word in ['documento', 'nota', 'nfe', 'nfce', 'cte', 'fiscal']):
            enhanced_context['query_type'] = 'document_analysis'
            enhanced_context['document_types'] = ['NFe', 'NFCe', 'CTe']

        elif any(word in query_lower for word in ['csv', 'planilha', 'dados', 'análise', 'estatística']):
            enhanced_context['query_type'] = 'csv_analysis'

        elif any(word in query_lower for word in ['financeiro', 'valor', 'total', 'imposto', 'receita', 'despesa']):
            enhanced_context['query_type'] = 'financial_analysis'

        elif any(word in query_lower for word in ['validação', 'erro', 'inconsistência', 'problema']):
            enhanced_context['query_type'] = 'validation_analysis'

        else:
            enhanced_context['query_type'] = 'general'

        # Set default limits
        enhanced_context.setdefault('limit', 10)

        return enhanced_context

    async def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get chat history for a session."""

        try:
            result = self.supabase.table('chat_messages').select('*').eq(
                'session_id', session_id
            ).order('created_at').execute()

            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Error getting session history: {e}")
            return []

    async def get_document_analysis(self, document_ids: List[str]) -> Dict[str, Any]:
        """Get detailed analysis for specific documents."""

        try:
            documents = []
            for doc_id in document_ids:
                summary = self.document_tool.get_document_summary(doc_id)
                if summary:
                    documents.append(summary)

            if not documents:
                return {'error': 'Nenhum documento encontrado'}

            # Generate insights
            insights = self.insight_generator.generate_financial_insights(
                [doc['document'] for doc in documents]
            )

            return {
                'documents': documents,
                'insights': insights,
                'summary': {
                    'total_documents': len(documents),
                    'document_types': list(set(doc['document'].get('document_type', 'Unknown')
                                             for doc in documents))
                }
            }

        except Exception as e:
            logger.error(f"Error getting document analysis: {e}")
            return {'error': str(e)}

    async def analyze_csv_data(self, csv_data: str) -> Dict[str, Any]:
        """Analyze CSV data and return insights."""

        try:
            analysis = self.csv_tool.analyze_csv_data(csv_data)

            if 'error' in analysis:
                return analysis

            # Generate insights
            insights = self.insight_generator.generate_csv_insights(analysis)

            return {
                'analysis': analysis,
                'insights': insights
            }

        except Exception as e:
            logger.error(f"Error analyzing CSV data: {e}")
            return {'error': str(e)}

    async def search_documents(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Search documents based on query and filters."""

        try:
            criteria = filters or {}

            # Add text search to criteria
            if query:
                # Search in extracted data JSON
                documents = self.supabase.table('fiscal_documents').select('*').execute()

                # Filter documents containing the query in extracted_data
                filtered_docs = []
                for doc in documents.data:
                    if self._document_matches_query(doc, query):
                        filtered_docs.append(doc)

                return {
                    'documents': filtered_docs[:20],  # Limit results
                    'total': len(filtered_docs),
                    'query': query
                }

            else:
                # Use criteria-based search
                documents = self.document_tool.get_documents_by_criteria(criteria, limit=20)
                return {
                    'documents': documents,
                    'total': len(documents),
                    'query': query
                }

        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return {'error': str(e), 'documents': [], 'total': 0}

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

    async def get_chat_sessions(self, user_id: str = None) -> List[Dict[str, Any]]:
        """Get list of chat sessions."""

        try:
            query = self.supabase.table('chat_sessions').select('*')

            if user_id:
                query = query.eq('user_id', user_id)

            result = query.order('created_at', desc=True).execute()
            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Error getting chat sessions: {e}")
            return []

    async def delete_session(self, session_id: str) -> bool:
        """Delete a chat session and all its messages."""

        try:
            # Messages will be deleted automatically due to CASCADE
            result = self.supabase.table('chat_sessions').delete().eq(
                'id', session_id
            ).execute()

            return len(result.data) > 0 if result.data else False

        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False
