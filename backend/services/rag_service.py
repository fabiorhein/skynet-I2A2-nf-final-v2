"""
RAG (Retrieval-Augmented Generation) Service.

This module orchestrates semantic search and response generation using Gemini
embeddings and vector search for intelligent Q&A on fiscal documents.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
import asyncio
from datetime import datetime
import streamlit as st
from backend.services.embedding_service import GeminiEmbeddingService
from backend.services.vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)


class RAGService:
    """
    Main RAG service that combines semantic search with Gemini response generation.

    This service handles the complete RAG pipeline:
    1. Query understanding and embedding
    2. Semantic search in document chunks
    3. Context retrieval and formatting
    4. Response generation using Gemini with context
    """

    def __init__(self):
        """
        Initialize the RAG service with embedding and vector store services.
        """
        # Use fallback embedding service instead of direct Gemini
        self.embedding_service = None
        self.vector_store = VectorStoreService()
        self._initialize_embedding_service()
        logger.info("RAGService initialized")

    def _initialize_embedding_service(self):
        """Initialize embedding service with fallback logic."""
        try:
            # Try to import and use fallback service
            from backend.services.fallback_embedding_service import FallbackEmbeddingService

            # Prefer free embeddings first (Sentence Transformers)
            self.embedding_service = FallbackEmbeddingService(preferred_provider="free")

            service_info = self.embedding_service.get_service_info()
            logger.info(f"✅ RAG embedding service ready: {service_info['primary_service']} (fallback: {service_info['fallback_service']})")

        except ImportError as e:
            logger.warning(f"Fallback embedding service not available: {e}")
            logger.info("💡 Run: python scripts/setup_free_embeddings.py")
            # Fallback to direct Gemini service
            self.embedding_service = GeminiEmbeddingService()
            logger.info("✅ Using direct Gemini embedding service")

        except Exception as e:
            logger.error(f"Failed to initialize any embedding service: {e}")
            raise

    async def answer_query(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_context_docs: int = 3,
        response_temperature: float = 0.1
    ) -> Dict[str, Any]:
        """
        Answer a query using RAG with semantic search and Gemini generation.

        Args:
            query: User's question about fiscal documents
            filters: Optional filters for document search
            max_context_docs: Maximum number of context documents to use
            response_temperature: Temperature for Gemini response generation

        Returns:
            Dictionary with answer, context, and metadata
        """
        try:
            logger.info(f"Processing RAG query: {query[:100]}...")

            # Step 1: Generate embedding for the query
            query_embedding = self.embedding_service.generate_query_embedding(query)

            # Step 2: Search for relevant document chunks
            similar_chunks = self.vector_store.search_similar_chunks(
                query_embedding=query_embedding,
                similarity_threshold=0.6,
                max_results=10,
                filters=filters
            )

            if not similar_chunks:
                logger.info("No similar chunks found - checking if any documents have embeddings")

                # Check if there are any documents with embeddings
                stats = self.vector_store.get_embedding_statistics()
                docs_with_embeddings = stats.get('documents_with_embeddings', 0)

                if docs_with_embeddings == 0:
                    logger.info("No documents with embeddings found")
                    return {
                        'answer': 'Nenhum documento foi processado para embeddings ainda. Use a aba "Processar Documento" para adicionar documentos ao sistema RAG.',
                        'context_docs': [],
                        'similar_chunks': [],
                        'total_chunks': 0,
                        'query_embedding_used': True,
                        'filters_applied': filters or {},
                        'status': 'no_documents'
                    }
                else:
                    logger.info(f"Found {docs_with_embeddings} documents with embeddings but no matches")
                    return {
                        'answer': f'Foram encontrados {docs_with_embeddings} documentos processados, mas nenhum relevante para sua consulta. Tente reformular a pergunta ou ajustar os filtros.',
                        'context_docs': [],
                        'similar_chunks': [],
                        'total_chunks': 0,
                        'query_embedding_used': True,
                        'filters_applied': filters or {},
                        'status': 'no_matches'
                    }

            # Step 3: Get document context for better responses
            context_docs = self.vector_store.get_document_context(
                query_embedding=query_embedding,
                max_documents=max_context_docs,
                max_chunks_per_document=2
            )

            # Step 4: Format context for the LLM
            context_text = self._format_context_for_llm(context_docs, similar_chunks)

            # Step 5: Generate response using Gemini with context
            answer = await self._generate_response_with_context(
                query=query,
                context=context_text,
                temperature=response_temperature
            )

            logger.info(f"RAG query completed successfully. Used {len(context_docs)} context documents")

            return {
                'answer': answer,
                'context_docs': context_docs,
                'similar_chunks': similar_chunks,
                'total_chunks': len(similar_chunks),
                'query_embedding_used': True,
                'filters_applied': filters or {},
                'status': 'success'
            }

        except Exception as e:
            logger.error(f"Error in RAG query processing: {str(e)}")
            return {
                'answer': f'Erro ao processar a consulta: {str(e)}. Tente novamente.',
                'context_docs': [],
                'similar_chunks': [],
                'total_chunks': 0,
                'query_embedding_used': False,
                'filters_applied': filters or {},
                'status': 'error',
                'error': str(e)
            }

    async def process_document_for_rag(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a fiscal document for RAG: split, embed, and store chunks.

        Args:
            document: Fiscal document data

        Returns:
            Processing result with statistics
        """
        try:
            logger.info(f"Processing document {document.get('id')} for RAG")

            # Update status to processing
            self.vector_store.update_document_embedding_status(document['id'], 'processing')

            # Process document: split and generate embeddings
            chunks_with_embeddings = self.embedding_service.process_document_for_embedding(document)

            if not chunks_with_embeddings:
                self.vector_store.update_document_embedding_status(document['id'], 'failed')
                return {
                    'success': False,
                    'error': 'No chunks generated or embedding failed',
                    'chunks_processed': 0,
                    'document_id': document['id']
                }

            # Save chunks to database
            saved_chunk_ids = self.vector_store.save_document_chunks(chunks_with_embeddings)

            # Update status to completed
            self.vector_store.update_document_embedding_status(document['id'], 'completed')

            logger.info(f"Document {document.get('id')} processed successfully: {len(saved_chunk_ids)} chunks saved")

            return {
                'success': True,
                'chunks_processed': len(saved_chunk_ids),
                'total_chunks': len(chunks_with_embeddings),
                'document_id': document['id'],
                'saved_chunk_ids': saved_chunk_ids
            }

        except Exception as e:
            logger.error(f"Error processing document for RAG: {str(e)}")
            self.vector_store.update_document_embedding_status(document['id'], 'failed')
            return {
                'success': False,
                'error': str(e),
                'chunks_processed': 0,
                'document_id': document['id']
            }

    def get_embedding_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the RAG system.

        Returns:
            Dictionary with system statistics
        """
        try:
            return self.vector_store.get_embedding_statistics()
        except Exception as e:
            logger.error(f"Error getting RAG statistics: {str(e)}")
            return {'error': str(e)}

    def _format_context_for_llm(self, context_docs: List[Dict[str, Any]], similar_chunks: List[Dict[str, Any]]) -> str:
        """
        Format document context for LLM consumption.

        Args:
            context_docs: Documents with relevant chunks
            similar_chunks: Individual similar chunks

        Returns:
            Formatted context string
        """
        if not context_docs and not similar_chunks:
            return "Nenhum documento relevante encontrado."

        context_parts = []

        # Add context from grouped documents
        if context_docs:
            context_parts.append("DOCUMENTOS RELEVANTES ENCONTRADOS:")
            context_parts.append("=" * 50)

            for i, doc in enumerate(context_docs, 1):
                context_parts.append(f"\nDOCUMENTO {i}:")
                context_parts.append(f"- Tipo: {doc.get('document_type', 'Não informado')}")
                context_parts.append(f"- CNPJ Emissor: {doc.get('issuer_cnpj', 'Não informado')}")
                context_parts.append(f"- Similaridade: {doc.get('total_similarity', 0):.3f}")
                context_parts.append(f"- Conteúdo Relevante: {doc.get('chunks_content', 'Sem conteúdo')[:500]}...")
                context_parts.append("-" * 30)

        # Add individual chunk details if needed
        if similar_chunks and len(similar_chunks) > len(context_docs):
            context_parts.append(f"\nTRECHOS ADICIONAIS ({len(similar_chunks) - len(context_docs)}):")
            for chunk in similar_chunks[len(context_docs):]:
                context_parts.append(f"- {chunk.get('content_text', '')[:200]}...")

        return "\n".join(context_parts)

    async def _generate_response_with_context(
        self,
        query: str,
        context: str,
        temperature: float = 0.1
    ) -> str:
        """
        Generate response using Gemini with RAG context.

        Args:
            query: Original user query
            context: Retrieved document context
            temperature: Response temperature for Gemini

        Returns:
            Generated response
        """
        try:
            import google.generativeai as genai
            from config import GOOGLE_API_KEY

            # Configure Gemini
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel('gemini-flash')

            # Create RAG prompt
            rag_prompt = f"""
Você é um especialista em análise de documentos fiscais. Use APENAS o contexto fornecido abaixo para responder à pergunta do usuário.

INSTRUÇÕES IMPORTANTES:
- Responda de forma clara, precisa e baseada apenas nos documentos fornecidos
- Se a informação não estiver no contexto, diga que não foi possível encontrar
- Mantenha um tom profissional e técnico
- Se houver dados numéricos, inclua valores exatos quando disponíveis
- Para consultas sobre valores, some apenas os valores explicitamente mencionados

CONTEXTO DOS DOCUMENTOS FISCAIS:
{context}

PERGUNTA DO USUÁRIO: {query}

RESPOSTA (baseada apenas no contexto acima):
"""

            # Generate response
            response = model.generate_content(
                rag_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=1000
                )
            )

            return response.text.strip()

        except Exception as e:
            logger.error(f"Error generating response with context: {str(e)}")
            return f"Erro ao gerar resposta: {str(e)}"

    async def validate_document_with_rag(
        self,
        document: Dict[str, Any],
        validation_rules: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Validate document fields using RAG context from similar documents.

        Args:
            document: Document to validate
            validation_rules: Specific validation rules to apply

        Returns:
            Validation results with insights
        """
        try:
            # Generate validation queries based on document type
            validation_queries = self._generate_validation_queries(document, validation_rules)

            validation_results = []

            for query in validation_queries:
                # Search for similar documents to validate against
                query_embedding = self.embedding_service.generate_query_embedding(query)

                similar_docs = self.vector_store.get_document_context(
                    query_embedding=query_embedding,
                    max_documents=5,
                    max_chunks_per_document=1
                )

                # Analyze validation based on similar documents
                validation_insight = self._analyze_validation(document, query, similar_docs)
                validation_results.append(validation_insight)

            # Save validation insights
            for insight in validation_results:
                if insight.get('confidence', 0) > 0.5:
                    self.vector_store.save_analysis_insight(
                        document_id=document['id'],
                        insight_type='validation',
                        insight_category='field_validation',
                        insight_text=insight['insight'],
                        confidence_score=insight['confidence'],
                        metadata=insight.get('metadata', {})
                    )

            return {
                'validation_results': validation_results,
                'document_id': document['id'],
                'validation_queries_used': len(validation_queries)
            }

        except Exception as e:
            logger.error(f"Error in document validation with RAG: {str(e)}")
            return {
                'validation_results': [],
                'document_id': document['id'],
                'error': str(e)
            }

    def _generate_validation_queries(self, document: Dict[str, Any], validation_rules: Optional[List[str]] = None) -> List[str]:
        """
        Generate validation queries based on document content.

        Args:
            document: Document to validate
            validation_rules: Specific rules to apply

        Returns:
            List of validation queries
        """
        queries = []

        # Default validation queries for fiscal documents
        if not validation_rules:
            validation_rules = [
                'document_format',
                'required_fields',
                'value_ranges',
                'issuer_validation'
            ]

        document_type = document.get('document_type', '')
        issuer_cnpj = document.get('issuer_cnpj', '')

        if 'document_format' in validation_rules:
            queries.append(f"Documentos do tipo {document_type} com formato correto")

        if 'required_fields' in validation_rules:
            queries.append(f"Campos obrigatórios para {document_type}")

        if 'value_ranges' in validation_rules and document.get('extracted_data'):
            total_value = document.get('extracted_data', {}).get('total', 0)
            queries.append(f"Valores típicos para documentos similares com valor próximo a {total_value}")

        if 'issuer_validation' in validation_rules and issuer_cnpj:
            queries.append(f"Documentos do emissor {issuer_cnpj} com padrões similares")

        return queries

    def _analyze_validation(
        self,
        document: Dict[str, Any],
        validation_query: str,
        similar_docs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze validation based on similar documents.

        Args:
            document: Document being validated
            validation_query: Validation query used
            similar_docs: Similar documents found

        Returns:
            Validation analysis result
        """
        if not similar_docs:
            return {
                'query': validation_query,
                'insight': 'Nenhum documento similar encontrado para validação',
                'confidence': 0.0,
                'metadata': {'similar_docs_count': 0}
            }

        # Analyze patterns in similar documents
        document_type = document.get('document_type', '')
        similar_types = [doc.get('document_type', '') for doc in similar_docs]
        type_consistency = similar_types.count(document_type) / len(similar_types) if similar_types else 0

        # Generate validation insight
        if type_consistency > 0.8:
            insight = f"Documento do tipo {document_type} é consistente com padrões encontrados em documentos similares."
        elif type_consistency > 0.5:
            insight = f"Documento do tipo {document_type} é parcialmente consistente. Verificar se o tipo está correto."
        else:
            insight = f"Documento do tipo {document_type} diverge dos padrões encontrados. Revisão recomendada."

        return {
            'query': validation_query,
            'insight': insight,
            'confidence': type_consistency,
            'metadata': {
                'similar_docs_count': len(similar_docs),
                'type_consistency': type_consistency,
                'similar_types': similar_types
            }
        }
