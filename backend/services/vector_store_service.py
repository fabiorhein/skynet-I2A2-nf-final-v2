"""
Vector Store Service for RAG system using PostgreSQL direct connection.

This module provides vector storage and semantic search functionality using direct
PostgreSQL connection with pgvector extension for efficient similarity search.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np
from psycopg2.extras import Json, RealDictCursor
from config import DATABASE_CONFIG

logger = logging.getLogger(__name__)


class VectorStoreService:
    """
    Service for vector storage and semantic search using direct PostgreSQL connection.

    Handles document chunk storage, embedding persistence, and similarity search
    operations for the RAG system using pgvector extension.
    """

    def __init__(self):
        """
        Initialize the vector store service with PostgreSQL direct connection.
        """
        self.db_config = DATABASE_CONFIG
        self._connection = None
        self._initialize_connection()
        logger.info("VectorStoreService initialized with PostgreSQL direct connection")

    def _initialize_connection(self):
        """Initialize PostgreSQL connection."""
        try:
            import psycopg2
            self._connection = psycopg2.connect(**self.db_config)
            self._connection.autocommit = True
            logger.debug("PostgreSQL connection established")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection: {e}")
            raise

    def _execute_query(self, query: str, params: tuple = None, fetch: str = "all") -> Any:
        """Execute a query with proper error handling."""
        try:
            if not self._connection or self._connection.closed:
                self._initialize_connection()

            with self._connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params or ())

                if fetch == "one":
                    return cursor.fetchone()
                elif fetch == "count":
                    result = cursor.fetchone()
                    return result['count'] if result else 0
                elif fetch is None:
                    # For queries that don't return data (UPDATE, DELETE, INSERT without RETURNING)
                    return cursor.rowcount
                else:
                    return cursor.fetchall()

        except Exception as e:
            logger.error(f"Database query error: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise

    def save_document_chunks(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """
        Save document chunks with embeddings to the database using direct PostgreSQL.

        Args:
            chunks: List of chunks with embeddings and metadata

        Returns:
            List of chunk IDs that were successfully saved
        """
        try:
            saved_ids = []
            query = """
                INSERT INTO document_chunks (fiscal_document_id, chunk_number, content_text, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """

            for chunk in chunks:
                if not chunk.get('embedding'):
                    logger.warning(f"Skipping chunk without embedding: {chunk.get('metadata', {}).get('chunk_number')}")
                    continue

                # Debug: Log the document ID being used
                doc_id_from_metadata = chunk['metadata'].get('document_id')
                logger.debug(f"Processing chunk {chunk['metadata']['chunk_number']} for document ID: {doc_id_from_metadata}")

                # Verify document exists before saving chunk
                doc_check_query = "SELECT id FROM fiscal_documents WHERE id = %s"
                doc_exists = self._execute_query(doc_check_query, (doc_id_from_metadata,), "one")

                if not doc_exists:
                    logger.error(f"Document {doc_id_from_metadata} not found in fiscal_documents table!")
                    logger.error(f"Available documents: {self._execute_query('SELECT COUNT(*) as count FROM fiscal_documents', fetch='count')}")

                    # List first few documents for debugging
                    docs_query = "SELECT id, file_name, document_type FROM fiscal_documents LIMIT 5"
                    docs = self._execute_query(docs_query)
                    logger.error(f"First few document IDs: {[d['id'][:8] for d in docs] if docs else 'No documents found'}")

                    for doc in docs or []:
                        logger.error(f"  - ID: {doc['id']}, File: {doc.get('file_name')}, Type: {doc.get('document_type')}")

                    continue  # Skip this chunk

                # Convert embedding to PostgreSQL vector format
                embedding = chunk['embedding']
                if isinstance(embedding, list):
                    embedding = np.array(embedding)

                # Prepare parameters
                params = (
                    doc_id_from_metadata,
                    chunk['metadata']['chunk_number'],
                    chunk['content_text'],
                    embedding.tolist(),  # Convert to list for JSON serialization
                    Json(chunk['metadata'])
                )

                result = self._execute_query(query, params, "one")

                if result:
                    saved_ids.append(str(result['id']))
                    logger.debug(f"Saved chunk {chunk['metadata']['chunk_number']} for document {doc_id_from_metadata}")
                else:
                    logger.error(f"Failed to save chunk {chunk['metadata']['chunk_number']}")

            logger.info(f"Successfully saved {len(saved_ids)}/{len(chunks)} chunks using PostgreSQL direct connection")
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
        Search for similar document chunks using semantic similarity with PostgreSQL direct.

        Args:
            query_embedding: Query embedding vector
            similarity_threshold: Minimum similarity score (0-1)
            max_results: Maximum number of results to return
            filters: Optional filters for document type, issuer, date range, etc.

        Returns:
            List of similar chunks with metadata and similarity scores
        """
        try:
            # Use pgvector for similarity search
            return self._search_similar_chunks_pgvector(query_embedding, similarity_threshold, max_results, filters)

        except Exception as e:
            logger.error(f"Error searching similar chunks: {str(e)}")
            return []

    def _search_similar_chunks_pgvector(
        self,
        query_embedding: List[float],
        similarity_threshold: float = 0.7,
        max_results: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Use pgvector for efficient similarity search with PostgreSQL direct connection.
        """
        try:
            # Convert query embedding to PostgreSQL vector format
            query_vector = np.array(query_embedding)

            # Base query with vector similarity using cosine similarity
            base_query = """
                SELECT
                    dc.id,
                    dc.fiscal_document_id,
                    dc.chunk_number,
                    dc.content_text,
                    dc.embedding,
                    dc.metadata,
                    dc.created_at,
                    1 - (dc.embedding <=> %s::vector) as similarity_score
                FROM document_chunks dc
                WHERE 1 - (dc.embedding <=> %s::vector) >= %s
            """

            params = [query_vector.tolist(), query_vector.tolist(), similarity_threshold]

            # Add filters if provided
            if filters:
                if filters.get('document_type'):
                    base_query += " AND EXISTS (SELECT 1 FROM fiscal_documents fd WHERE fd.id = dc.fiscal_document_id AND fd.document_type = %s)"
                    params.append(filters['document_type'])

                if filters.get('issuer_cnpj'):
                    base_query += " AND EXISTS (SELECT 1 FROM fiscal_documents fd WHERE fd.id = dc.fiscal_document_id AND fd.issuer_cnpj = %s)"
                    params.append(filters['issuer_cnpj'])

                if filters.get('date_from') or filters.get('date_to'):
                    base_query += " AND EXISTS (SELECT 1 FROM fiscal_documents fd WHERE fd.id = dc.fiscal_document_id"
                    if filters.get('date_from'):
                        base_query += " AND fd.created_at >= %s"
                        params.append(filters['date_from'])
                    if filters.get('date_to'):
                        base_query += " AND fd.created_at <= %s"
                        params.append(filters['date_to'])
                    base_query += ")"

            # Order by similarity and limit results
            base_query += " ORDER BY dc.embedding <=> %s::vector LIMIT %s"
            params.extend([query_vector.tolist(), max_results])

            results = self._execute_query(base_query, tuple(params))

            if not results:
                logger.info("No chunks found with pgvector similarity search")
                return []

            # Get additional document information for each chunk
            similar_chunks = []
            for result in results:
                # Get document info
                doc_query = """
                    SELECT file_name, document_type, document_number, issuer_cnpj, extracted_data, validation_status, classification
                    FROM fiscal_documents WHERE id = %s
                """
                doc_info = self._execute_query(doc_query, (result['fiscal_document_id'],), "one")

                if doc_info:
                    similar_chunks.append({
                        'id': str(result['id']),
                        'fiscal_document_id': str(result['fiscal_document_id']),
                        'chunk_number': result['chunk_number'],
                        'content_text': result['content_text'],
                        'embedding': result['embedding'],
                        'metadata': result['metadata'],
                        'similarity_score': float(result['similarity_score']),
                        'file_name': doc_info['file_name'],
                        'document_type': doc_info['document_type'],
                        'document_number': doc_info['document_number'],
                        'issuer_cnpj': doc_info['issuer_cnpj'],
                        'extracted_data': doc_info['extracted_data'],
                        'validation_status': doc_info['validation_status'],
                        'classification': doc_info['classification'],
                        'created_at': result['created_at']
                    })

            logger.info(f"Pgvector search found {len(similar_chunks)} similar chunks")
            return similar_chunks

        except Exception as e:
            logger.error(f"Error in pgvector search: {str(e)}")
            return []

    def get_document_context(
        self,
        query_embedding: List[float],
        max_documents: int = 3,
        max_chunks_per_document: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Get relevant document context for RAG responses using PostgreSQL direct.

        Args:
            query_embedding: Query embedding vector
            max_documents: Maximum number of documents to include
            max_chunks_per_document: Maximum chunks per document

        Returns:
            List of documents with their relevant chunks
        """
        try:
            # Get similar chunks first
            similar_chunks = self._search_similar_chunks_pgvector(
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
                doc_query = "SELECT * FROM fiscal_documents WHERE id = %s"
                doc_info = self._execute_query(doc_query, (doc_id,), "one")

                if doc_info:
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

            logger.info(f"PostgreSQL query retrieved context from {len(context_docs)} documents")
            return context_docs

        except Exception as e:
            logger.error(f"Error getting document context: {str(e)}")
            return []

    def update_document_embedding_status(self, document_id: str, status: str) -> bool:
        """
        Update the embedding processing status of a document using PostgreSQL direct.

        Args:
            document_id: Fiscal document ID
            status: New status ('pending', 'processing', 'completed', 'failed')

        Returns:
            True if update was successful
        """
        try:
            query = """
                UPDATE fiscal_documents
                SET embedding_status = %s, last_embedding_update = %s
                WHERE id = %s
            """
            result = self._execute_query(query, (status, datetime.now().isoformat(), document_id), fetch=None)

            # For UPDATE queries, check rowcount instead of result
            success = result > 0
            if success:
                logger.debug(f"Updated embedding status for document {document_id} to {status}")
            else:
                logger.error(f"Failed to update embedding status for document {document_id} - document may not exist")

            return success

        except Exception as e:
            logger.error(f"Error updating embedding status for document {document_id}: {str(e)}")
            return False

    def delete_document_chunks(self, document_id: str) -> bool:
        """
        Delete all chunks for a specific document using PostgreSQL direct.

        Args:
            document_id: Fiscal document ID

        Returns:
            True if deletion was successful
        """
        try:
            query = "DELETE FROM document_chunks WHERE fiscal_document_id = %s"
            result = self._execute_query(query, (document_id,), fetch=None)

            # For DELETE queries, rowcount indicates success (0 or more rows deleted)
            success = True  # DELETE succeeds if no error occurs
            if success:
                logger.debug(f"Deleted {result} chunks for document {document_id}")
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
        Save an analysis insight for a document using PostgreSQL direct.

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
            query = """
                INSERT INTO analysis_insights (fiscal_document_id, insight_type, insight_category, insight_text, confidence_score, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """

            params = (
                document_id,
                insight_type,
                insight_category,
                insight_text,
                max(0.0, min(1.0, confidence_score)),  # Clamp to 0-1
                Json(metadata or {})
            )

            result = self._execute_query(query, params, "one")

            if result:
                insight_id = str(result['id'])
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
        Get analysis insights for a document using PostgreSQL direct.

        Args:
            document_id: Fiscal document ID
            insight_type: Optional filter by insight type

        Returns:
            List of insights
        """
        try:
            if insight_type:
                query = "SELECT * FROM analysis_insights WHERE fiscal_document_id = %s AND insight_type = %s ORDER BY confidence_score DESC"
                params = (document_id, insight_type)
            else:
                query = "SELECT * FROM analysis_insights WHERE fiscal_document_id = %s ORDER BY confidence_score DESC"
                params = (document_id,)

            results = self._execute_query(query, params)

            insights = []
            for result in results:
                # Convert JSONB fields back to dict
                insight = dict(result)
                if insight.get('metadata'):
                    insight['metadata'] = insight['metadata'] if isinstance(insight['metadata'], dict) else {}
                insights.append(insight)

            logger.debug(f"Retrieved {len(insights)} insights for document {document_id}")
            return insights

        except Exception as e:
            logger.error(f"Error getting insights for document {document_id}: {str(e)}")
            return []

    def get_embedding_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the embedding system using PostgreSQL direct.

        Returns:
            Dictionary with embedding statistics
        """
        try:
            # Count total chunks
            chunks_query = "SELECT COUNT(*) as count FROM document_chunks"
            chunks_result = self._execute_query(chunks_query, fetch="one")
            total_chunks = chunks_result['count'] if chunks_result else 0

            # Count documents with embeddings
            docs_query = "SELECT COUNT(*) as count FROM fiscal_documents WHERE embedding_status = 'completed'"
            docs_result = self._execute_query(docs_query, fetch="one")
            docs_with_embeddings = docs_result['count'] if docs_result else 0

            # Count total insights
            insights_query = "SELECT COUNT(*) as count FROM analysis_insights"
            insights_result = self._execute_query(insights_query, fetch="one")
            total_insights = insights_result['count'] if insights_result else 0

            # Get embedding status distribution
            status_query = "SELECT embedding_status, COUNT(*) as count FROM fiscal_documents GROUP BY embedding_status"
            status_results = self._execute_query(status_query)
            status_counts = {row['embedding_status']: row['count'] for row in status_results}

            return {
                'total_chunks': total_chunks,
                'documents_with_embeddings': docs_with_embeddings,
                'total_insights': total_insights,
                'embedding_status_distribution': status_counts,
                'vector_dimension': 768,
                'connection_type': 'postgresql_direct'
            }

        except Exception as e:
            logger.error(f"Error getting embedding statistics: {str(e)}")
            return {
                'error': str(e),
                'total_chunks': 0,
                'documents_with_embeddings': 0,
                'total_insights': 0,
                'embedding_status_distribution': {},
                'vector_dimension': 768,
                'connection_type': 'postgresql_direct'
            }

    def get_chunks_by_document(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific document using PostgreSQL direct.

        Args:
            document_id: Fiscal document ID

        Returns:
            List of document chunks
        """
        try:
            query = "SELECT * FROM document_chunks WHERE fiscal_document_id = %s ORDER BY chunk_number"
            results = self._execute_query(query, (document_id,))

            chunks = []
            for result in results:
                chunk = dict(result)
                # Convert metadata JSONB back to dict
                if chunk.get('metadata'):
                    chunk['metadata'] = chunk['metadata'] if isinstance(chunk['metadata'], dict) else {}
                chunks.append(chunk)

            logger.debug(f"Retrieved {len(chunks)} chunks for document {document_id}")
            return chunks

        except Exception as e:
            logger.error(f"Error getting chunks for document {document_id}: {str(e)}")
            raise

    def close(self):
        """Close the database connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.info("VectorStore PostgreSQL connection closed")

    def __del__(self):
        """Cleanup when the service is destroyed."""
        self.close()
