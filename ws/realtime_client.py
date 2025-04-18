
import asyncio

from typing import Any, Literal, Optional, AsyncContextManager
from collections.abc import AsyncGenerator

from asyncer import create_task_group
from pydantic import BaseModel


class RealtimeEvent(BaseModel):
    raw_message: dict[str, Any]


class RealtimeClientBase:
    def __init__(self, connection: AsyncGenerator[dict[str, Any], None]):
        self._eventQueue = asyncio.Queue()
        self._connection = connection

    async def add_event(self, event: Optional[RealtimeEvent]):
        await self._eventQueue.put(event)

    async def get_event(self) -> Optional[RealtimeEvent]:
        return await self._eventQueue.get()

        # everything is run in the same task group to enable easy cancellation using self._tg.cancel_scope.cancel()
    async def _read_from_connection_task(self):
        async for event in self._read_from_connection():
            await self.add_event(event)
        await self.add_event(None)

    async def _read_from_connection(self) -> AsyncGenerator[RealtimeEvent, None]:
        """Read messages from the OpenAI Realtime API."""
        async for message in self._connection:
            for event in self._parse_message(message.model_dump()):
                yield event
 
    async def _read_events(self) -> AsyncGenerator[RealtimeEvent, None]:
        """Read events from a Realtime Client."""
        async with create_task_group() as tg:
            tg.start_soon(self._read_from_connection_task)
            while True:
                try:
                    event = await self._eventQueue.get()
                    if event is not None:
                        yield event
                    else:
                        break
                except Exception:
                    break
    
    async def read_events(self) -> AsyncGenerator[RealtimeEvent, None]:
        """Read messages from the OpenAI Realtime API."""
        if self._connection is None:
            raise RuntimeError("Client is not connected, call connect() first.")

        try:
            async for event in self._read_events():
                yield event

        finally:
            self._connection = None


    def connect(self) -> AsyncContextManager[None]: ...

    
