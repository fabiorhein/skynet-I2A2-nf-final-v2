-- 011b-add_embedding_indexes.sql
-- Add performance indexes for embeddings (run this after 011-add_rag_support.sql)

SELECT 'Starting embedding performance indexes migration...' as migration_status;

-- Create HNSW index for vector similarity search (this can be slow, run separately)
-- Uncomment when you have some data and want to optimize search performance
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw
ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- Optional: Create IVFFlat index as alternative (faster to create, slightly slower queries)
-- CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_ivfflat
-- ON document_chunks USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);

SELECT 'Embedding performance indexes migration completed successfully' as migration_status;
