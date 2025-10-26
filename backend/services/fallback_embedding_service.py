"""
Fallback Embedding Service - Combines free and paid embeddings.

This service automatically tries free embeddings first, then falls back to paid
embeddings if there's an error or if free embeddings are not available.
"""
import logging
from typing import List, Dict, Any, Optional
from backend.services.free_embedding_service import FreeEmbeddingService

logger = logging.getLogger(__name__)

class FallbackEmbeddingService:
    """
    Embedding service with automatic fallback between free and paid options.

    This service provides a unified interface for embeddings and automatically
    switches between free (local) and paid (API) embedding services based on
    availability and preference.
    """

    def __init__(self, preferred_provider: str = "free", gemini_model: str = "models/embedding-001"):
        """
        Initialize fallback embedding service.

        Args:
            preferred_provider: "free" (default) or "paid"
            gemini_model: Gemini model name for paid embeddings
        """
        self.preferred_provider = preferred_provider
        self.gemini_model = gemini_model

        # Initialize both services
        self.free_service = None
        self.paid_service = None

        # Try to import and initialize services
        self._initialize_services()

        # Choose primary service based on preference and availability
        self._setup_primary_service()

    def _initialize_services(self):
        """Initialize both free and paid services."""
        # Initialize free service (Sentence Transformers)
        try:
            self.free_service = FreeEmbeddingService()
            logger.info("✅ Free embedding service (Sentence Transformers) ready")
        except Exception as e:
            logger.warning(f"Free embedding service failed to initialize: {e}")
            logger.info("💡 Install with: pip install sentence-transformers torch")

        # Initialize paid service (Gemini)
        try:
            # Import here to avoid errors if not available
            from backend.services.embedding_service import GeminiEmbeddingService
            self.paid_service = GeminiEmbeddingService(model_name=self.gemini_model)
            logger.info(f"✅ Paid embedding service (Gemini) ready: {self.gemini_model}")
        except Exception as e:
            logger.warning(f"Paid embedding service failed to initialize: {e}")
            logger.info("💡 Check your GOOGLE_API_KEY in .streamlit/secrets.toml")

    def _setup_primary_service(self):
        """Set up primary and fallback services based on preference."""
        if self.preferred_provider == "free" and self.free_service:
            self.primary_service = self.free_service
            self.fallback_service = self.paid_service
            logger.info("🚀 Primary: Free embeddings (Sentence Transformers)")
        elif self.paid_service:
            self.primary_service = self.paid_service
            self.fallback_service = self.free_service
            logger.info("🚀 Primary: Paid embeddings (Gemini)")
        else:
            logger.error("❌ No embedding service available!")
            raise RuntimeError("No embedding service could be initialized")

        if self.fallback_service:
            fallback_type = "Free" if self.fallback_service == self.free_service else "Paid"
            logger.info(f"🔄 Fallback: {fallback_type} embeddings available")

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding with automatic fallback.

        Tries primary service first, then fallback if it fails.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector

        Raises:
            RuntimeError: If both services fail
        """
        errors = []

        # Try primary service first
        if self.primary_service:
            try:
                logger.debug(f"Using primary service: {'Free (Sentence Transformers)' if self.primary_service == self.free_service else 'Paid (Gemini)'}")
                return self.primary_service.generate_embedding(text)
            except Exception as e:
                error_msg = f"Primary service failed: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)

        # Try fallback service
        if self.fallback_service:
            try:
                fallback_type = "Free (Sentence Transformers)" if self.fallback_service == self.free_service else "Paid (Gemini)"
                logger.info(f"Switching to fallback service: {fallback_type}")
                return self.fallback_service.generate_embedding(text)
            except Exception as e:
                error_msg = f"Fallback service failed: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # If both failed, raise comprehensive error
        error_summary = "All embedding services failed:\n" + "\n".join(f"  - {err}" for err in errors)
        logger.error(error_summary)
        raise RuntimeError(error_summary)

    def generate_query_embedding(self, query: str) -> List[float]:
        """
        Generate query embedding with fallback.

        Same logic as generate_embedding, but optimized for search queries.

        Args:
            query: Search query text

        Returns:
            Query embedding vector
        """
        return self.generate_embedding(query)  # Same implementation

    def get_service_info(self) -> Dict[str, Any]:
        """
        Get information about available services.

        Returns:
            Dictionary with service status and configuration
        """
        return {
            'preferred_provider': self.preferred_provider,
            'primary_service': 'free' if self.primary_service == self.free_service else 'paid',
            'fallback_service': 'free' if self.fallback_service == self.free_service else 'paid',
            'free_available': self.free_service is not None,
            'paid_available': self.paid_service is not None,
            'total_services': sum([self.free_service is not None, self.paid_service is not None]),
            'gemini_model': self.gemini_model if self.paid_service else None
        }

    def switch_to_free(self):
        """Switch primary service to free embeddings."""
        if self.free_service:
            self.preferred_provider = "free"
            self.primary_service = self.free_service
            self.fallback_service = self.paid_service
            logger.info("🔄 Switched to free embeddings as primary")
        else:
            logger.warning("Cannot switch to free embeddings - service not available")

    def switch_to_paid(self):
        """Switch primary service to paid embeddings."""
        if self.paid_service:
            self.preferred_provider = "paid"
            self.primary_service = self.paid_service
            self.fallback_service = self.free_service
            logger.info("🔄 Switched to paid embeddings as primary")
        else:
            logger.warning("Cannot switch to paid embeddings - service not available")

    def is_free_available(self) -> bool:
        """Check if free embeddings are available."""
        return self.free_service is not None

    def is_paid_available(self) -> bool:
        """Check if paid embeddings are available."""
        return self.paid_service is not None

    def get_embedding_dimension(self) -> int:
        """
        Get embedding dimension from primary service.

        Returns:
            Embedding dimension or 0 if no service available
        """
        if self.primary_service:
            if hasattr(self.primary_service, 'embedding_dimension'):
                return self.primary_service.embedding_dimension
            elif hasattr(self.primary_service, 'get_model_info'):
                return self.primary_service.get_model_info().get('embedding_dimension', 0)

        return 0
