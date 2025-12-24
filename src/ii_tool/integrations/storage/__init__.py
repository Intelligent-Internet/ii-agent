"""This module is duplicated with src/ii_agent/storage"""
# NOTE: to avoid circular import, future refactor maybe move to a "common" package

from .base import BaseStorage
from .gcs import GCS
from .local import LocalStorage
from .factory import create_storage_client
from .config import StorageConfig


__all__ = ["BaseStorage", "GCS", "LocalStorage", "create_storage_client", "StorageConfig"]