"""Generic Redis pub/sub service for distributed messaging."""

import asyncio
import inspect
import json
import logging
from typing import Any, Callable, Dict, Optional
from socketio import AsyncRedisManager
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from ii_agent.core.config.ii_agent_config import IIAgentConfig

logger = logging.getLogger(__name__)


def create_session_manager(config: IIAgentConfig) -> AsyncRedisManager | None:
    if not config.redis_session_enabled:
        return None

    if config.is_redis_ssl:
        # For SSL connections (Upstash, cloud Redis), pass SSL options to redis_options
        import ssl

        return AsyncRedisManager(
            url=config.redis_session_url,
            redis_options={
                "ssl_cert_reqs": ssl.CERT_NONE,  # Skip certificate verification for cloud Redis
                "ssl_check_hostname": False,  # Don't check hostname
                "decode_responses": False,  # Socket.IO requires bytes, not strings
            },
        )

    # For non-SSL connections
    return AsyncRedisManager(
        url=config.redis_session_url,
        redis_options={"decode_responses": False},  # Socket.IO requires bytes
    )


class RedisPubSub:
    """Generic Redis-based pub/sub service for distributed messaging.

    This service provides a simple interface for publishing and subscribing to
    Redis channels across multiple server instances.

    Features:
    - Thread-safe handler management with asyncio.Lock
    - Automatic message serialization/deserialization
    - Multiple channel subscription support
    - Graceful error handling and cleanup
    """

    def __init__(
        self,
        redis_client: Redis,
        namespace: str = "default",
    ):
        """Initialize Redis pub/sub service.

        Args:
            redis_client: Existing Redis client instance to reuse
            namespace: Namespace for organizing channels
        """
        self._namespace = namespace
        self._redis_client = redis_client
        self._pubsub: Optional[PubSub] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._handlers: Dict[str, Callable[[Any], None]] = {}
        self._is_listening = False
        self._handler_lock = asyncio.Lock()

    def _make_channel(self, channel: str) -> str:
        """Create namespaced channel name."""
        return f"{self._namespace}:{channel}"

    async def publish(self, channel: str, message: Any) -> int:
        """Publish a message to a channel.

        Args:
            channel: The channel name to publish to
            message: The message to publish (will be JSON serialized)

        Returns:
            Number of subscribers that received the message
        """
        namespaced_channel = self._make_channel(channel)

        try:
            # Serialize message to JSON
            serialized_message = json.dumps(message)

            result = await self._redis_client.publish(
                namespaced_channel, serialized_message
            )
            logger.debug(
                f"Published message to channel {channel}, {result} subscriber(s) received it"
            )

            return result
        except Exception as e:
            logger.error(
                f"Failed to publish message to channel {channel}: {e}", exc_info=True
            )
            raise

    async def subscribe(self, channel: str, handler: Callable[[Any], None]) -> None:
        """Subscribe to messages on a channel.

        Args:
            channel: The channel name to subscribe to
            handler: Callback function to handle messages
        """
        namespaced_channel = self._make_channel(channel)

        async with self._handler_lock:
            self._handlers[namespaced_channel] = handler
            logger.info(f"Registered handler for namespaced channel: {namespaced_channel}")

            if self._pubsub is None:
                self._pubsub = self._redis_client.pubsub()

            try:
                await self._pubsub.subscribe(namespaced_channel)
                logger.info(f"Subscribed to Redis channel: {channel} (namespaced: {namespaced_channel})")

                if not self._is_listening:
                    self._listener_task = asyncio.create_task(
                        self._listen_for_messages()
                    )
                    self._is_listening = True
                    logger.info("Started Redis pub/sub listener task")

            except Exception as e:
                logger.error(
                    f"Failed to subscribe to channel {channel}: {e}", exc_info=True
                )
                raise

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from messages on a channel.

        Args:
            channel: The channel name to unsubscribe from
        """
        namespaced_channel = self._make_channel(channel)

        async with self._handler_lock:
            if namespaced_channel in self._handlers:
                del self._handlers[namespaced_channel]

            if self._pubsub:
                try:
                    await self._pubsub.unsubscribe(namespaced_channel)
                    logger.info(f"Unsubscribed from channel: {channel}")

                    if not self._handlers and self._listener_task:
                        self._listener_task.cancel()
                        try:
                            await self._listener_task
                        except asyncio.CancelledError:
                            pass
                        self._listener_task = None
                        self._is_listening = False
                except Exception as e:
                    logger.error(
                        f"Failed to unsubscribe from channel {channel}: {e}",
                        exc_info=True,
                    )

    async def _listen_for_messages(self) -> None:
        """Listen for messages on subscribed channels.

        Thread-safe message handling with lock protection.
        """
        if not self._pubsub:
            return

        logger.info(f"Starting Redis pub/sub listener in namepace: {self._namespace}")

        try:
            async for message in self._pubsub.listen():
                data = message["data"]
                message_type = message["type"]
                message_channel = message.get("channel")
                if message_type == "subscribe":
                    continue
                try:
                    logger.debug(f"Received message with type: {message_type} on channel: {message_channel}")
                    # Deserialize message from JSON
                    message_data = json.loads(data)
                    async with self._handler_lock:
                        # Use the actual channel from the message, not the parameter
                        if message_channel and message_channel in self._handlers:
                            handler = self._handlers[message_channel]
                        else:
                            handler = None

                    if handler:
                        try:
                            if inspect.iscoroutinefunction(handler):
                                await handler(message_data)
                            else:
                                handler(message_data)
                        except Exception as handler_error:
                            logger.error(
                                f"Error in handler for {message_channel}: {handler_error}",
                                exc_info=True,
                            )
                    else:
                        logger.debug(
                            f"No handler registered for channel {message_channel}, message dropped"
                        )

                except json.JSONDecodeError as e:
                    logger.error(
                        f"Failed to decode message from {message_channel}: {e}",
                        exc_info=True,
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message from {message_channel}: {e}",
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            logger.info("Redis pub/sub listener cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in Redis pub/sub listener: {e}", exc_info=True)
            self._is_listening = False
            raise

    async def close(self) -> None:
        """Clean up resources and close pubsub connection."""
        logger.info("Closing Redis pub/sub service")

        # Cancel listener task
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        # Close pubsub connection
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None

        self._handlers.clear()
        self._is_listening = False
        logger.info("Redis pub/sub service closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
