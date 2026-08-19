"""Enum types for memory domain."""

from enum import StrEnum


class MemorySortField(StrEnum):
    UPDATED_AT = "updated_at"
    MEMORY = "memory"
    TOPICS_COUNT = "topics_count"


class MemorySortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"
