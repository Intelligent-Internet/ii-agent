"""Utility modules for the WebSocket server."""

from .error_handling import send_error_event, handle_service_error

__all__ = ["send_error_event", "handle_service_error"]