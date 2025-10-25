-- 010-convert_embedding_to_vector.sql
-- Convert embedding_vector from TEXT to VECTOR type

-- Check if vector extension is available
SELECT 'Checking if vector extension is available...';

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
        THEN 'Vector extension available, proceeding with conversion'
        ELSE 'Vector extension not available, skipping conversion'
    END as conversion_status;

-- Only proceed if vector extension is available and column needs conversion
SELECT 'Checking if column needs conversion...';

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
             AND EXISTS (SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'document_summaries'
                        AND column_name = 'embedding_vector'
                        AND data_type = 'text')
        THEN 'Converting column to VECTOR type...'
        ELSE 'No conversion needed'
    END as conversion_action;

-- Perform the conversion if conditions are met
SELECT 'Attempting column conversion...';

-- This will only work if vector extension exists and column is TEXT type
ALTER TABLE document_summaries
ALTER COLUMN embedding_vector TYPE VECTOR(1536)
USING CASE
    WHEN embedding_vector IS NOT NULL AND embedding_vector != ''
    THEN embedding_vector::vector
    ELSE NULL
END;