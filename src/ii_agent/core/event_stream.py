import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Callable, List, Set
from threading import Lock

from ii_agent.core.event import RealtimeEvent


class EventStream(ABC):
    """Abstract base class for event streaming."""

    @abstractmethod
    def add_event(self, event: RealtimeEvent) -> None:
        """Add an event to the stream."""
        pass

    @abstractmethod
    def subscribe(self, callback: Callable[[RealtimeEvent], None]) -> None:
        """Subscribe to events in the stream."""
        pass

    @abstractmethod
    def unsubscribe(self, callback: Callable[[RealtimeEvent], None]) -> None:
        """Unsubscribe from events in the stream."""
        pass


class AsyncEventStream(EventStream):
    """Async implementation of EventStream that manages event subscribers."""

    def __init__(self, logger: logging.Logger = None):
        self._subscribers: Set[Callable[[RealtimeEvent], None]] = set()
        self._async_subscribers: Set[Callable[[RealtimeEvent], asyncio.coroutine]] = set()
        self._lock = Lock()
        self._logger = logger or logging.getLogger(__name__)

    def add_event(self, event: RealtimeEvent) -> None:
        """Add an event to the stream and notify all subscribers."""
        with self._lock:
            subscribers = self._subscribers.copy()
            async_subscribers = self._async_subscribers.copy()

        # Notify sync subscribers
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                self._logger.error(f"Error in event subscriber: {e}")

        # Notify async subscribers
        for callback in async_subscribers:
            try:
                asyncio.create_task(callback(event))
            except Exception as e:
                self._logger.error(f"Error in async event subscriber: {e}")

    def subscribe(self, callback: Callable[[RealtimeEvent], None]) -> None:
        """Subscribe to events in the stream."""
        with self._lock:
            if asyncio.iscoroutinefunction(callback):
                self._async_subscribers.add(callback)
            else:
                self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable[[RealtimeEvent], None]) -> None:
        """Unsubscribe from events in the stream."""
        with self._lock:
            self._subscribers.discard(callback)
            self._async_subscribers.discard(callback)

    def clear_subscribers(self) -> None:
        """Remove all subscribers."""
        with self._lock:
            self._subscribers.clear()
            self._async_subscribers.clear()