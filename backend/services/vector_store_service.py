"""
Vector Store Service for RAG system.

This module provides vector storage and semantic search functionality using Supabase
with pgvector extension for efficient similarity search in fiscal documents.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
import json
from datetime import datetime
import streamlit as st
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)


class VectorStoreService:
    """
    Service for vector storage and semantic search using Supabase with pgvector.

    Handles document chunk storage, embedding persistence, and similarity search
    operations for the RAG system.
    """

    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """
        Initialize the vector store service.

        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase API key
        """
        self.supabase_url = supabase_url or SUPABASE_URL
        self.supabase_key = supabase_key or SUPABASE_KEY

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY are required")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        logger.info("VectorStoreService initialized")

    def save_document_chunks(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """
        Save document chunks with embeddings to the database.

        Args:
            chunks: List of chunks with embeddings and metadata

        Returns:
            List of chunk IDs that were successfully saved

        Raises:
            Exception: If saving fails
        """
        try:
            saved_ids = []

            for chunk in chunks:
                if not chunk.get('embedding'):
                    logger.warning(f"Skipping chunk without embedding: {chunk.get('metadata', {}).get('chunk_number')}")
                    continue

                # Debug: Log the document ID being used
                doc_id_from_metadata = chunk['metadata'].get('document_id')
                logger.debug(f"Processing chunk {chunk['metadata']['chunk_number']} for document ID: {doc_id_from_metadata}")

                # Verify document exists before saving chunk
                doc_check = self.supabase.table('fiscal_documents').select('id').eq('id', doc_id_from_metadata).execute()
                if not doc_check.data:
                    logger.error(f"Document {doc_id_from_metadata} not found in fiscal_documents table!")
                    logger.error(f"Available documents: {len([d for d in self.supabase.table('fiscal_documents').select('id').execute().data or []])}")
                    logger.error(f"First few document IDs: {[d['id'][:8] for d in (self.supabase.table('fiscal_documents').select('id').limit(5).execute().data or [])]}")

                    # Try to get the document with more details
                    all_docs = self.supabase.table('fiscal_documents').select('id, file_name, document_type').execute()
                    logger.error(f"All documents in table: {len(all_docs.data or [])}")
                    for doc in (all_docs.data or [])[:3]:
                        logger.error(f"  - ID: {doc['id']}, File: {doc.get('file_name')}, Type: {doc.get('document_type')}")

                    continue  # Skip this chunk

                chunk_data = {
                    'fiscal_document_id': chunk['metadata']['document_id'],
                    'chunk_number': chunk['metadata']['chunk_number'],
                    'content_text': chunk['content_text'],
                    'embedding': chunk['embedding'],
                    'metadata': chunk['metadata']
                }

                # Insert chunk into database
                result = self.supabase.table('document_chunks').insert(chunk_data).execute()

                if result.data:
                    saved_ids.append(str(result.data[0]['id']))
                    logger.debug(f"Saved chunk {chunk['metadata']['chunk_number']} for document {chunk['metadata']['document_id']}")
                else:
                    logger.error(f"Failed to save chunk {chunk['metadata']['chunk_number']}")

            logger.info(f"Successfully saved {len(saved_ids)}/{len(chunks)} chunks")
            return saved_ids

        except Exception as e:
            logger.error(f"Error saving document chunks: {str(e)}")
            raise

    def search_similar_chunks(
        self,
        query_embedding: List[float],
        similarity_threshold: float = 0.7,
        max_results: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar document chunks using semantic similarity.

        Uses direct SQL queries with pgvector for maximum compatibility.

        Args:
            query_embedding: Query embedding vector
            similarity_threshold: Minimum similarity score (0-1)
            max_results: Maximum number of results to return
            filters: Optional filters for document type, issuer, date range, etc.

        Returns:
            List of similar chunks with metadata and similarity scores
        """
        try:
            # Use direct table queries instead of RPC functions
            return self._search_similar_chunks_direct(query_embedding, similarity_threshold, max_results, filters)

        except Exception as e:
            logger.error(f"Error searching similar chunks: {str(e)}")
            return []

    def _search_similar_chunks_direct(
        self,
        query_embedding: List[float],
        similarity_threshold: float = 0.7,
        max_results: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Direct table query for semantic search (main method).
        """
        try:
            # Build query with filters
            query = self.supabase.table('document_chunks').select(
                'id, fiscal_document_id, chunk_number, content_text, embedding, metadata'
            )

            # Apply filters at the query level
            if filters:
                if filters.get('document_type'):
                    # Get document IDs that match the filter first
                    doc_ids_result = self.supabase.table('fiscal_documents').select('id').eq(
                        'document_type', filters['document_type']
                    ).execute()

                    if doc_ids_result.data:
                        doc_ids = [doc['id'] for doc in doc_ids_result.data]
                        query = query.in_('fiscal_document_id', doc_ids)

                if filters.get('issuer_cnpj'):
                    doc_ids_result = self.supabase.table('fiscal_documents').select('id').eq(
                        'issuer_cnpj', filters['issuer_cnpj']
                    ).execute()

                    if doc_ids_result.data:
                        doc_ids = [doc['id'] for doc in doc_ids_result.data]
                        query = query.in_('fiscal_document_id', doc_ids)

                if filters.get('date_from') or filters.get('date_to'):
                    # For date filters, we need to join and filter
                    date_query = self.supabase.table('document_chunks').select(
                        'document_chunks.id, document_chunks.fiscal_document_id, document_chunks.chunk_number, '
                        'document_chunks.content_text, document_chunks.embedding, document_chunks.metadata'
                    ).join(
                        'fiscal_documents', 'document_chunks.fiscal_document_id', 'fiscal_documents.id'
                    )

                    if filters.get('date_from'):
                        date_query = date_query.gte('fiscal_documents.created_at', filters['date_from'])
                    if filters.get('date_to'):
                        date_query = date_query.lte('fiscal_documents.created_at', filters['date_to'])

                    all_chunks_result = date_query.execute()
                else:
                    all_chunks_result = query.execute()
            else:
                all_chunks_result = query.execute()

            if not all_chunks_result.data:
                logger.info("No chunks found with applied filters")
                return []

            # Filter by similarity in Python (less efficient but works everywhere)
            similar_chunks = []

            for chunk in all_chunks_result.data:
                if chunk.get('embedding'):
                    # Calculate similarity
                    chunk_embedding = chunk['embedding']
                    if isinstance(chunk_embedding, list) and len(chunk_embedding) == len(query_embedding):
                        # Simple cosine similarity calculation
                        import numpy as np
                        vec1 = np.array(query_embedding)
                        vec2 = np.array(chunk_embedding)

                        dot_product = np.dot(vec1, vec2)
                        norm1 = np.linalg.norm(vec1)
                        norm2 = np.linalg.norm(vec2)

                        if norm1 > 0 and norm2 > 0:
                            similarity = dot_product / (norm1 * norm2)

                            if similarity >= similarity_threshold:
                                # Get additional document info
                                doc_result = self.supabase.table('fiscal_documents').select(
                                    'file_name, document_type, document_number, issuer_cnpj, extracted_data, validation_status, classification'
                                ).eq('id', chunk['fiscal_document_id']).execute()

                                if doc_result.data:
                                    doc_info = doc_result.data[0]
                                    similar_chunks.append({
                                        'id': chunk['id'],
                                        'fiscal_document_id': chunk['fiscal_document_id'],
                                        'chunk_number': chunk['chunk_number'],
                                        'content_text': chunk['content_text'],
                                        'embedding': chunk['embedding'],
                                        'metadata': chunk['metadata'],
                                        'similarity_score': float(similarity),
                                        'file_name': doc_info['file_name'],
                                        'document_type': doc_info['document_type'],
                                        'document_number': doc_info['document_number'],
                                        'issuer_cnpj': doc_info['issuer_cnpj'],
                                        'extracted_data': doc_info['extracted_data'],
                                        'validation_status': doc_info['validation_status'],
                                        'classification': doc_info['classification']
                                    })

            # Sort by similarity and limit results
            similar_chunks.sort(key=lambda x: x['similarity_score'], reverse=True)
            similar_chunks = similar_chunks[:max_results]

            logger.info(f"Direct query found {len(similar_chunks)} similar chunks")
            return similar_chunks

        except Exception as e:
            logger.error(f"Error in direct search: {str(e)}")
            return []

    def get_document_context(
        self,
        query_embedding: List[float],
        max_documents: int = 3,
        max_chunks_per_document: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Get relevant document context for RAG responses.

        Args:
            query_embedding: Query embedding vector
            max_documents: Maximum number of documents to include
            max_chunks_per_document: Maximum chunks per document

        Returns:
            List of documents with their relevant chunks
        """
        try:
            # Use direct query method
            return self._get_document_context_direct(query_embedding, max_documents, max_chunks_per_document)

        except Exception as e:
            logger.error(f"Error getting document context: {str(e)}")
            return []

    def _get_document_context_direct(
        self,
        query_embedding: List[float],
        max_documents: int = 3,
        max_chunks_per_document: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Direct query for document context (fallback method).
        """
        try:
            # Get similar chunks first
            similar_chunks = self._search_similar_chunks_direct(
                query_embedding, 0.5, max_documents * max_chunks_per_document
            )

            if not similar_chunks:
                return []

            # Group by document
            from collections import defaultdict
            doc_groups = defaultdict(list)

            for chunk in similar_chunks:
                doc_id = chunk['fiscal_document_id']
                doc_groups[doc_id].append(chunk)

            # Build context for each document
            context_docs = []

            for doc_id, chunks in list(doc_groups.items())[:max_documents]:
                # Get document info
                doc_result = self.supabase.table('fiscal_documents').select('*').eq('id', doc_id).execute()

                if doc_result.data:
                    doc_info = doc_result.data[0]

                    # Sort chunks by similarity and take top ones
                    chunks.sort(key=lambda x: x['similarity_score'], reverse=True)
                    top_chunks = chunks[:max_chunks_per_document]

                    # Combine chunk content
                    chunks_content = '\n\n'.join([chunk['content_text'] for chunk in top_chunks])

                    context_docs.append({
                        'fiscal_document_id': doc_id,
                        'file_name': doc_info['file_name'],
                        'document_type': doc_info['document_type'],
                        'document_number': doc_info['document_number'],
                        'issuer_cnpj': doc_info['issuer_cnpj'],
                        'total_similarity': sum(chunk['similarity_score'] for chunk in top_chunks) / len(top_chunks),
                        'chunks_content': chunks_content,
                        'chunks_count': len(top_chunks)
                    })

            logger.info(f"Direct query retrieved context from {len(context_docs)} documents")
            return context_docs

        except Exception as e:
            logger.error(f"Error in direct context query: {str(e)}")
            return []

    def get_chunks_by_document(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific document.

        Args:
            document_id: Fiscal document ID

        Returns:
            List of document chunks
        """
        try:
            result = self.supabase.table('document_chunks').select('*').eq('fiscal_document_id', document_id).execute()

            if result.data:
                logger.debug(f"Retrieved {len(result.data)} chunks for document {document_id}")
                return result.data
            else:
                logger.debug(f"No chunks found for document {document_id}")
                return []

        except Exception as e:
            logger.error(f"Error getting chunks for document {document_id}: {str(e)}")
            raise

    def update_document_embedding_status(self, document_id: str, status: str) -> bool:
        """
        Update the embedding processing status of a document.

        Args:
            document_id: Fiscal document ID
            status: New status ('pending', 'processing', 'completed', 'failed')

        Returns:
            True if update was successful
        """
        try:
            result = self.supabase.table('fiscal_documents').update({
                'embedding_status': status,
                'last_embedding_update': datetime.now().isoformat()
            }).eq('id', document_id).execute()

            success = bool(result.data)
            if success:
                logger.debug(f"Updated embedding status for document {document_id} to {status}")
            else:
                logger.error(f"Failed to update embedding status for document {document_id}")

            return success

        except Exception as e:
            logger.error(f"Error updating embedding status for document {document_id}: {str(e)}")
            return False

    def delete_document_chunks(self, document_id: str) -> bool:
        """
        Delete all chunks for a specific document.

        Args:
            document_id: Fiscal document ID

        Returns:
            True if deletion was successful
        """
        try:
            result = self.supabase.table('document_chunks').delete().eq('fiscal_document_id', document_id).execute()

            success = bool(result.data) or True  # DELETE returns empty data on success
            if success:
                logger.debug(f"Deleted chunks for document {document_id}")
            else:
                logger.error(f"Failed to delete chunks for document {document_id}")

            return success

        except Exception as e:
            logger.error(f"Error deleting chunks for document {document_id}: {str(e)}")
            return False

    def save_analysis_insight(
        self,
        document_id: str,
        insight_type: str,
        insight_category: str,
        insight_text: str,
        confidence_score: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Save an analysis insight for a document.

        Args:
            document_id: Fiscal document ID
            insight_type: Type of insight ('financial', 'tax', 'operational', 'trend')
            insight_category: Category of insight
            insight_text: The insight text
            confidence_score: Confidence score (0.0 to 1.0)
            metadata: Additional metadata

        Returns:
            Insight ID if saved successfully, None otherwise
        """
        try:
            insight_data = {
                'fiscal_document_id': document_id,
                'insight_type': insight_type,
                'insight_category': insight_category,
                'insight_text': insight_text,
                'confidence_score': max(0.0, min(1.0, confidence_score)),  # Clamp to 0-1
                'metadata': metadata or {}
            }

            result = self.supabase.table('analysis_insights').insert(insight_data).execute()

            if result.data:
                insight_id = str(result.data[0]['id'])
                logger.debug(f"Saved analysis insight {insight_id} for document {document_id}")
                return insight_id
            else:
                logger.error(f"Failed to save analysis insight for document {document_id}")
                return None

        except Exception as e:
            logger.error(f"Error saving analysis insight for document {document_id}: {str(e)}")
            return None

    def get_document_insights(self, document_id: str, insight_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get analysis insights for a document.

        Args:
            document_id: Fiscal document ID
            insight_type: Optional filter by insight type

        Returns:
            List of insights
        """
        try:
            query = self.supabase.table('analysis_insights').select('*').eq('fiscal_document_id', document_id)

            if insight_type:
                query = query.eq('insight_type', insight_type)

            result = query.order('confidence_score', desc=True).execute()

            if result.data:
                logger.debug(f"Retrieved {len(result.data)} insights for document {document_id}")
                return result.data
            else:
                logger.debug(f"No insights found for document {document_id}")
                return []

        except Exception as e:
            logger.error(f"Error getting insights for document {document_id}: {str(e)}")
            return []

    def get_embedding_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the embedding system.

        Returns:
            Dictionary with embedding statistics
        """
        try:
            # Count total chunks
            chunks_result = self.supabase.table('document_chunks').select('id', count='exact').execute()
            total_chunks = chunks_result.count if chunks_result.count is not None else 0

            # Count documents with embeddings
            docs_result = self.supabase.table('fiscal_documents').select('id', count='exact').eq('embedding_status', 'completed').execute()
            docs_with_embeddings = docs_result.count if docs_result.count is not None else 0

            # Count total insights
            insights_result = self.supabase.table('analysis_insights').select('id', count='exact').execute()
            total_insights = insights_result.count if insights_result.count is not None else 0

            # Get embedding status distribution
            status_result = self.supabase.table('fiscal_documents').select('embedding_status').execute()
            status_counts = {}
            if status_result.data:
                for row in status_result.data:
                    status = row['embedding_status']
                    status_counts[status] = status_counts.get(status, 0) + 1

            return {
                'total_chunks': total_chunks,
                'documents_with_embeddings': docs_with_embeddings,
                'total_insights': total_insights,
                'embedding_status_distribution': status_counts,
                'vector_dimension': 768
            }

        except Exception as e:
            logger.error(f"Error getting embedding statistics: {str(e)}")
            return {
                'error': str(e),
                'total_chunks': 0,
                'documents_with_embeddings': 0,
                'total_insights': 0,
                'embedding_status_distribution': {},
                'vector_dimension': 768
            }
