"""Asynchronous RAG worker that consumes embedding jobs and processes documents."""
from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from typing import Any, Dict, Optional

from backend.database.storage_manager import get_storage
from backend.services.embedding_job_service import EmbeddingJobService
from backend.services.rag_service import RAGService
from backend.services.vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")


class RAGWorker:
    """Background worker that pulls embedding jobs and processes documents."""

    def __init__(
        self,
        *,
        poll_interval: float = 2.0,
        max_concurrent_jobs: int = 2,
    ) -> None:
        self.poll_interval = max(0.5, poll_interval)
        self.semaphore = asyncio.Semaphore(max(1, max_concurrent_jobs))
        self._stopping = asyncio.Event()

        self.storage = get_storage()
        self.vector_store = VectorStoreService()
        self.job_service = EmbeddingJobService()
        self.rag_service = RAGService(self.vector_store)

    async def start(self) -> None:
        """Start the worker loop until stop() is called."""
        logger.info("🚀 RAG worker started")
        while not self._stopping.is_set():
            try:
                jobs = self.job_service.fetch_next_jobs(limit=self.semaphore._value)
                if not jobs:
                    await asyncio.sleep(self.poll_interval)
                    continue

                await asyncio.gather(*(self._handle_job(job) for job in jobs))
            except asyncio.CancelledError:
                logger.info("Worker cancelled, shutting down...")
                break
            except Exception as exc:
                logger.exception("Unexpected error in worker loop: %s", exc)
                await asyncio.sleep(self.poll_interval)

        logger.info("👋 Worker stopped")

    async def stop(self) -> None:
        """Signal the worker to stop."""
        self._stopping.set()

    async def _handle_job(self, job: Dict[str, Any]) -> None:
        """Process a single embedding job."""
        async with self.semaphore:
            job_id = job.get('id')
            document_id = job.get('document_id')
            logger.info("Processing job %s for document %s", job_id, document_id)

            try:
                document = self.storage.get_fiscal_document(document_id)
                if not document:
                    raise RuntimeError(f"Documento {document_id} não encontrado")

                result = await self.rag_service.process_document_for_rag(document)
                if not result.get('success'):
                    raise RuntimeError(result.get('error', 'Falha desconhecida no processamento RAG'))

                self.job_service.mark_completed(job_id)
                logger.info(
                    "✅ Job %s concluído (%s chunks)",
                    job_id,
                    result.get('chunks_processed', 0),
                )
            except Exception as exc:
                logger.error("Erro ao processar job %s: %s", job_id, exc)
                self.job_service.mark_failed(job, str(exc))

    @staticmethod
    def run() -> None:
        """Entry point for running the worker with graceful shutdown."""
        worker = RAGWorker()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _run() -> None:
            stop_event = asyncio.Event()

            def _signal_handler(*_: Any) -> None:
                logger.info("Signal received, stopping worker...")
                worker._stopping.set()
                stop_event.set()

            for sig in (signal.SIGINT, signal.SIGTERM):
                with suppress(NotImplementedError):
                    loop.add_signal_handler(sig, _signal_handler)

            worker_task = asyncio.create_task(worker.start())
            await stop_event.wait()
            await worker.stop()
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task

        try:
            loop.run_until_complete(_run())
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()


if __name__ == "__main__":
    RAGWorker.run()
