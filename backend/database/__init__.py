"""
Database package for the application.

This package provides storage implementations and database utilities.
"""

from .base_storage import (
    StorageInterface,
    StorageType,
    StorageError,
    PaginatedResponse,
    generate_id,
    get_current_timestamp
)

from .postgresql_storage import PostgreSQLStorage, PostgreSQLStorageError
from .local_storage import LocalJSONStorage, LocalStorageError
from .storage_manager import StorageManager, storage_manager, get_storage

__all__ = [
    # Base types and interfaces
    'StorageInterface',
    'StorageType',
    'StorageError',
    'PaginatedResponse',
    'generate_id',
    'get_current_timestamp',

    # Storage implementations
    'PostgreSQLStorage',
    'PostgreSQLStorageError',
    'LocalJSONStorage',
    'LocalStorageError',

    # Storage management
    'StorageManager',
    'storage_manager',
    'get_storage',
]
