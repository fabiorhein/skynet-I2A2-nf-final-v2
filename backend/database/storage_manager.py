"""
Storage manager for the application.
Handles initialization and switching between storage backends.
"""
import logging
from typing import Optional

from config import SUPABASE_URL, SUPABASE_KEY, DATABASE_CONFIG
from .base_storage import StorageInterface, StorageType
from .local_storage import LocalJSONStorage, LocalStorageError

# Import PostgreSQL storage with error handling
try:
    from .postgresql_storage import PostgreSQLStorage, PostgreSQLStorageError
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    PostgreSQLStorage = None
    PostgreSQLStorageError = Exception

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Centralized storage manager for the application.
    Ensures consistent storage status across all components.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StorageManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._storage: Optional[StorageInterface] = None
        self._status = "🔃 Inicializando armazenamento..."
        self._status_type = "info"  # Can be "info", "success", "warning", or "error"
        self._initialize_storage()

    def _initialize_storage(self):
        """Initialize the appropriate storage backend."""
        try:
            # First, try to use PostgreSQL if credentials are available
            if self._has_postgresql_config() and POSTGRESQL_AVAILABLE:
                try:
                    self._storage = PostgreSQLStorage()
                    self._test_postgresql_connection()
                    self._status = "✅ Conectado ao PostgreSQL (via psycopg2)"
                    self._status_type = "success"
                except PostgreSQLStorageError as e:
                    logger.warning(f"PostgreSQL connection failed ({e}), falling back to local storage")
                    self._storage = LocalJSONStorage()
                    self._status = "⚠️ Falha na conexão PostgreSQL, usando armazenamento local"
                    self._status_type = "warning"
                except Exception as e:
                    logger.warning(f"PostgreSQL error ({e}), falling back to local storage")
                    self._storage = LocalJSONStorage()
                    self._status = "⚠️ Erro no PostgreSQL, usando armazenamento local"
                    self._status_type = "warning"
            else:
                if not POSTGRESQL_AVAILABLE:
                    self._storage = LocalJSONStorage()
                    self._status = "⚠️ PostgreSQL não disponível (módulo psycopg2), usando armazenamento local"
                    self._status_type = "warning"
                else:
                    raise ValueError("PostgreSQL configuration not available")

        except (Exception) as e:
            # Fall back to local storage
            logger.warning(f"Storage initialization failed ({e}), falling back to local storage")
            self._storage = LocalJSONStorage()
            self._status = "⚠️ Usando armazenamento local (arquivos JSON)"
            self._status_type = "warning"
            logger.error(f"Error initializing storage: {str(e)}")

    def _has_postgresql_config(self) -> bool:
        """Check if PostgreSQL configuration is available."""
        required_fields = ['dbname', 'user', 'password', 'host', 'port']
        return all(DATABASE_CONFIG.get(field) for field in required_fields)

    def _test_postgresql_connection(self):
        """Test PostgreSQL connection."""
        try:
            # Try to execute a simple query
            self._storage.get_fiscal_documents(page=1, page_size=1)
        except Exception as query_error:
            # If the table doesn't exist, we'll still consider the connection successful
            if "relation" in str(query_error).lower() and "does not exist" in str(query_error).lower():
                logger.info("Connected to PostgreSQL but tables don't exist yet")
                self._status = "✅ Conectado ao PostgreSQL (tabelas não encontradas)"
                self._status_type = "warning"
            else:
                raise query_error

    @property
    def storage(self) -> StorageInterface:
        """Get the storage instance."""
        if self._storage is None:
            self._initialize_storage()
        return self._storage

    @property
    def storage_type(self) -> StorageType:
        """Get the current storage type."""
        if POSTGRESQL_AVAILABLE and isinstance(self._storage, PostgreSQLStorage):
            return StorageType.POSTGRESQL
        else:
            return StorageType.LOCAL_JSON

    @property
    def status(self) -> str:
        """Get the current storage status message."""
        return self._status

    @property
    def status_type(self) -> str:
        """Get the status type for display (info, success, warning, error)."""
        return self._status_type

    def display_status(self, container=None):
        """Display the storage status in the provided container or the sidebar.

        Args:
            container: Streamlit container to display the status in. If None, uses the sidebar.
        """
        try:
            import streamlit as st
            display = container if container is not None else st.sidebar

            if self._status_type == "success":
                display.success(self._status)
            elif self._status_type == "warning":
                display.warning(self._status)
            elif self._status_type == "error":
                display.error(self._status)
            else:
                display.info(self._status)
        except ImportError:
            # Streamlit not available
            print(f"Storage Status: {self._status}")

    @property
    def supabase_client(self):
        """Get a Supabase client instance for chat system compatibility."""
        try:
            from supabase import create_client

            if not SUPABASE_URL or not SUPABASE_KEY:
                # If no Supabase credentials, return a mock client that raises errors
                class MockClient:
                    def table(self, table_name):
                        raise AttributeError("Supabase not configured - check your credentials")
                return MockClient()

            # Create a real Supabase client
            client = create_client(SUPABASE_URL, SUPABASE_KEY)
            return client

        except ImportError:
            # If supabase package not available, return a mock client
            class MockClient:
                def table(self, table_name):
                    raise AttributeError("Supabase client not available - install supabase-py")
            return MockClient()
        except Exception as e:
            # If any other error, return a mock client
            class MockClient:
                def table(self, table_name):
                    raise AttributeError(f"Failed to create Supabase client: {e}")
            return MockClient()

    def close(self):
        """Close any open connections."""
        if hasattr(self._storage, 'close'):
            self._storage.close()

    def __del__(self):
        """Cleanup when the manager is destroyed."""
        self.close()


# Global instance
storage_manager = StorageManager()

# Backward compatibility - expose storage methods at module level
def get_storage() -> StorageInterface:
    """Get the current storage instance."""
    return storage_manager.storage

def get_storage_type() -> StorageType:
    """Get the current storage type."""
    return storage_manager.storage_type
