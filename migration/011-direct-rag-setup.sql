-- 011-direct-rag-setup.sql
-- Direct SQL to create RAG tables (run this in Supabase SQL Editor if Python migration times out)

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create document_chunks table for RAG system
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fiscal_document_id UUID NOT NULL REFERENCES fiscal_documents(id) ON DELETE CASCADE,
    chunk_number INTEGER NOT NULL,
    content_text TEXT NOT NULL,
    embedding VECTOR(768),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fiscal_document_id, chunk_number)
);

-- Create analysis_insights table for structured insights
CREATE TABLE IF NOT EXISTS analysis_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fiscal_document_id UUID NOT NULL REFERENCES fiscal_documents(id) ON DELETE CASCADE,
    insight_type VARCHAR NOT NULL,
    insight_category VARCHAR,
    insight_text TEXT NOT NULL,
    confidence_score DECIMAL(3,2) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add RAG columns to fiscal_documents table
ALTER TABLE fiscal_documents
ADD COLUMN IF NOT EXISTS document_type VARCHAR,
ADD COLUMN IF NOT EXISTS document_data JSONB,
ADD COLUMN IF NOT EXISTS embedding_status VARCHAR DEFAULT 'pending' CHECK (embedding_status IN ('pending', 'processing', 'completed', 'failed')),
ADD COLUMN IF NOT EXISTS last_embedding_update TIMESTAMPTZ;

-- Create essential indexes only
CREATE INDEX IF NOT EXISTS idx_document_chunks_fiscal_document_id
ON document_chunks(fiscal_document_id);

CREATE INDEX IF NOT EXISTS idx_analysis_insights_document_id
ON analysis_insights(fiscal_document_id);

CREATE INDEX IF NOT EXISTS idx_fiscal_documents_embedding_status
ON fiscal_documents(embedding_status);

-- Grant permissions
GRANT SELECT ON document_chunks TO authenticated;
GRANT SELECT ON analysis_insights TO authenticated;
GRANT INSERT, UPDATE ON document_chunks TO authenticated;
GRANT INSERT ON analysis_insights TO authenticated;

-- Add comments
COMMENT ON TABLE document_chunks IS 'Document chunks with embeddings for RAG';
COMMENT ON TABLE analysis_insights IS 'Analysis insights from fiscal documents';
COMMENT ON COLUMN document_chunks.embedding IS '768-dimensional vector embeddings';
