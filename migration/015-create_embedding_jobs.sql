-- Create embedding job queue table for background RAG processing
CREATE TABLE IF NOT EXISTS embedding_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES fiscal_documents(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    payload JSONB DEFAULT '{}'::jsonb,
    available_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embedding_jobs_status_priority ON embedding_jobs (status, priority DESC, available_at, created_at);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_document ON embedding_jobs (document_id);
