"""Embedding job queue service for managing background RAG processing tasks."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json
    PSYCOPG2_AVAILABLE = True
except ImportError:  # pragma: no cover - handled by runtime checks
    PSYCOPG2_AVAILABLE = False  # type: ignore
    RealDictCursor = Json = None  # type: ignore

from config import DATABASE_CONFIG

logger = logging.getLogger(__name__)


class EmbeddingJobServiceError(RuntimeError):
    """Embedding job specific error."""


class EmbeddingJobService:
    """Service that manages the lifecycle of embedding queue jobs."""

    def __init__(self, retry_delay_seconds: int = 300):
        if not PSYCOPG2_AVAILABLE:
            raise EmbeddingJobServiceError(
                "psycopg2 is required for EmbeddingJobService. Install with: pip install psycopg2-binary"
            )

        self.db_config = DATABASE_CONFIG
        self.retry_delay_seconds = max(0, retry_delay_seconds)
        self._connection: Optional[psycopg2.extensions.connection] = None

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _get_connection(self):
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(**self.db_config)
            # Autocommit enables us to run queue operations as single statements
            self._connection.autocommit = True
            logger.debug("EmbeddingJobService connected to PostgreSQL")
        return self._connection

    def close(self):
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.debug("EmbeddingJobService connection closed")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enqueue_document(
        self,
        document_id: str,
        *,
        priority: int = 0,
        payload: Optional[Dict[str, Any]] = None,
        available_at: Optional[datetime] = None,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        """Create a new embedding job for the given document."""
        if not document_id:
            raise ValueError("document_id is required to enqueue an embedding job")

        conn = self._get_connection()
        payload_json = Json(payload or {})
        available = available_at or datetime.utcnow()

        query = """
            INSERT INTO embedding_jobs (document_id, priority, payload, available_at, max_attempts)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, document_id, status, priority, attempts, max_attempts, created_at, updated_at
        """

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (document_id, priority, payload_json, available, max_attempts))
            job = cursor.fetchone()
            logger.info("Enqueued embedding job %s for document %s", job['id'], document_id)
            return dict(job)

    def fetch_next_jobs(self, limit: int = 1) -> List[Dict[str, Any]]:
        """Fetch the next pending jobs and mark them as processing."""
        limit = max(1, limit)
        conn = self._get_connection()

        query = """
        WITH next_jobs AS (
            SELECT id
            FROM embedding_jobs
            WHERE status = 'pending'
              AND available_at <= NOW()
            ORDER BY priority DESC, available_at, created_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        UPDATE embedding_jobs AS ej
        SET status = 'processing',
            attempts = ej.attempts + 1,
            updated_at = NOW()
        FROM next_jobs
        WHERE ej.id = next_jobs.id
        RETURNING ej.*
        """

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (limit,))
            jobs = cursor.fetchall() or []
            if jobs:
                logger.debug("Fetched %s embedding jobs for processing", len(jobs))
            return [dict(job) for job in jobs]

    def mark_completed(self, job_id: str) -> None:
        """Mark a job as completed."""
        if not job_id:
            return

        conn = self._get_connection()
        query = """
            UPDATE embedding_jobs
            SET status = 'completed', last_error = NULL, updated_at = NOW()
            WHERE id = %s
        """

        with conn.cursor() as cursor:
            cursor.execute(query, (job_id,))
            logger.info("Embedding job %s completed", job_id)

    def mark_failed(
        self,
        job: Dict[str, Any],
        error: str,
        *,
        retry: bool = True,
    ) -> None:
        """Mark a job as failed and optionally requeue it."""
        job_id = job.get('id') if isinstance(job, dict) else job
        if not job_id:
            return

        attempts = job.get('attempts', 0) if isinstance(job, dict) else 0
        max_attempts = job.get('max_attempts', 3) if isinstance(job, dict) else 3
        should_retry = retry and attempts < max_attempts

        conn = self._get_connection()

        if should_retry:
            query = """
                UPDATE embedding_jobs
                SET status = 'pending',
                    last_error = %s,
                    available_at = NOW() + (%s * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE id = %s
            """
            params = (error[:1000], self.retry_delay_seconds, job_id)
            log_msg = "Embedding job %s failed (attempt %s/%s) - requeued"
        else:
            query = """
                UPDATE embedding_jobs
                SET status = 'failed',
                    last_error = %s,
                    updated_at = NOW()
                WHERE id = %s
            """
            params = (error[:1000], job_id)
            log_msg = "Embedding job %s failed permanently after %s attempts"

        with conn.cursor() as cursor:
            cursor.execute(query, params)
            logger.warning(log_msg, job_id, attempts, max_attempts)

    def heartbeat(self, job_id: str) -> None:
        """Update the heartbeat timestamp for long running jobs."""
        if not job_id:
            return
        conn = self._get_connection()
        query = """
            UPDATE embedding_jobs
            SET updated_at = NOW()
            WHERE id = %s
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (job_id,))

    def get_stats(self) -> Dict[str, int]:
        """Return aggregated statistics about the queue."""
        conn = self._get_connection()
        query = """
            SELECT status, COUNT(*) as count
            FROM embedding_jobs
            GROUP BY status
        """
        stats: Dict[str, int] = {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0}
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query)
            results = cursor.fetchall() or []
            for row in results:
                stats[row['status']] = row['count']
        return stats

    def purge_completed(self, older_than: timedelta) -> int:
        """Delete completed jobs older than the given duration."""
        conn = self._get_connection()
        query = """
            DELETE FROM embedding_jobs
            WHERE status = 'completed'
              AND updated_at < NOW() - (%s * INTERVAL '1 second')
        """
        seconds = int(older_than.total_seconds())
        with conn.cursor() as cursor:
            cursor.execute(query, (seconds,))
            deleted = cursor.rowcount or 0
            if deleted:
                logger.info("Purged %s completed embedding jobs", deleted)
            return deleted

    def __del__(self):  # pragma: no cover - defensive cleanup
        try:
            self.close()
        except Exception:
            pass
