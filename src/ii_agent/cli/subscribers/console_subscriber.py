"""
Console subscriber for CLI output.

This module provides real-time console output for agent events.
"""

import sys
import time
from typing import Optional, Dict, Any
from threading import Lock

from ii_agent.core.event import RealtimeEvent, EventType
from ii_agent.core.config.llm_config import LLMConfig


class ConsoleSubscriber:
    """Subscriber that handles console output for agent events."""
    
    def __init__(self, minimal: bool = False):
        self.minimal = minimal
        self._lock = Lock()
        self._current_tool_call: Optional[Dict[str, Any]] = None
        self._thinking_indicator = False
        
    def handle_event(self, event: RealtimeEvent) -> None:
        """Handle an event by outputting to console."""
        with self._lock: 
            if event.type == EventType.AGENT_THINKING:
                self._handle_thinking_event(event)
            elif event.type == EventType.TOOL_CALL:
                self._handle_tool_call_event(event)
            elif event.type == EventType.TOOL_RESULT:
                self._handle_tool_result_event(event)
            elif event.type == EventType.AGENT_RESPONSE:
                self._handle_agent_response_event(event)
            elif event.type == EventType.AGENT_RESPONSE_INTERRUPTED:
                self._handle_interrupted_event(event)
            elif event.type == EventType.ERROR:
                self._handle_error_event(event)
            elif event.type == EventType.PROCESSING:
                self._handle_processing_event(event)
    
    def _handle_thinking_event(self, event: RealtimeEvent) -> None:
        """Handle agent thinking event."""
        if not self._thinking_indicator:
            self._print_status("🤔 Agent is thinking...")
            self._thinking_indicator = True
    
    def _handle_tool_call_event(self, event: RealtimeEvent) -> None:
        """Handle tool call event."""
        self._clear_thinking_indicator()
        
        content = event.content
        tool_name = content.get("tool_name", "unknown")
        tool_input = content.get("tool_input", {})
        
        self._current_tool_call = content
        
        if not self.minimal:
            self._print_tool_call(tool_name, tool_input)
        else:
            self._print_status(f"🔧 Using tool: {tool_name}")
    
    def _handle_tool_result_event(self, event: RealtimeEvent) -> None:
        """Handle tool result event."""
        content = event.content
        tool_name = content.get("tool_name", "unknown")
        result = content.get("result", "")
        
        if not self.minimal:
            self._print_tool_result(tool_name, result)
        else:
            self._print_status(f"✅ Tool completed: {tool_name}")
        
        self._current_tool_call = None
    
    def _handle_agent_response_event(self, event: RealtimeEvent) -> None:
        """Handle agent response event."""
        self._clear_thinking_indicator()
        
        content = event.content
        text = content.get("text", "")
        
        if text.strip():
            self._print_response(text)
    
    def _handle_interrupted_event(self, event: RealtimeEvent) -> None:
        """Handle interrupted event."""
        self._clear_thinking_indicator()
        
        content = event.content
        text = content.get("text", "")
        
        self._print_error(f"⚠️ Interrupted: {text}")
    
    def _handle_error_event(self, event: RealtimeEvent) -> None:
        """Handle error event."""
        self._clear_thinking_indicator()
        
        content = event.content
        error_msg = content.get("error", "Unknown error")
        
        self._print_error(f"❌ Error: {error_msg}")
    
    def _handle_processing_event(self, event: RealtimeEvent) -> None:
        """Handle processing event."""
        content = event.content
        message = content.get("message", "Processing...")
        self._print_status(f"⏳ {message}")
    
    def _print_status(self, message: str) -> None:
        """Print status message."""
        print(f"\r{message}", end="\n", flush=True)
    
    def _print_response(self, text: str) -> None:
        """Print agent response."""
        # Clear any status indicators
        self._clear_thinking_indicator()
        
        print("\n" + "="*50)
        print("🤖 Agent Response:")
        print("="*50)
        print(text)
        print("="*50 + "\n")
    
    def _print_tool_call(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        """Print detailed tool call information."""
        print(f"\n🔧 Tool Call: {tool_name}")
        print("-" * 30)
        
        if tool_input:
            for key, value in tool_input.items():
                # Truncate long values
                if isinstance(value, str) and len(value) > 10000:
                    value = value[:10000] + "..."
                print(f"  {key}: {value}")
        
        print("-" * 30)
    
    def _print_tool_result(self, tool_name: str, result: str) -> None:
        """Print tool result."""
        print(f"\n✅ Tool Result: {tool_name}")
        print("-" * 30)
        
        # Truncate long results in minimal mode
        if len(result) > 10000:
            result = result[:10000] + "\n... (truncated)"
        
        print(result)
        print("-" * 30)
    
    def _print_error(self, message: str) -> None:
        """Print error message."""
        print(f"\n{message}", file=sys.stderr)
    
    def _clear_thinking_indicator(self) -> None:
        """Clear the thinking indicator."""
        if self._thinking_indicator:
            # Clear the line
            print("\r" + " " * 50 + "\r", end="", flush=True)
            self._thinking_indicator = False
    
    def print_welcome(self) -> None:
        """Print welcome message."""
        if not self.minimal:
            print("\n" + "=" * 50)
            print("🚀 Intelligent Internet Agent - CLI")
            print("=" * 50)
            print("  Type 'exit' or 'quit' to end the session")
            print("  Use Ctrl+C to interrupt the agent")
            print("=" * 50 + "\n")
    
    def print_goodbye(self) -> None:
        """Print goodbye message."""
        if not self.minimal:
            print("\n" + "=" * 30)
            print("👋 Session ended. Goodbye!")
            print("=" * 30 + "\n")
    
    def print_session_info(self, session_name: Optional[str] = None) -> None:
        """Print session information."""
        if not self.minimal and session_name:
            print(f"\n📝 Active Session")
            print("-" * 20)
            print(f"  Name: {session_name}")
            print("-" * 20)
    
    def print_config_info(self, config: LLMConfig) -> None:
        """Print configuration information."""
        if not self.minimal:
            print("\n🔧 Agent Configuration")
            print("=" * 40)
            
            # Extract key config attributes
            config_items = []
            
            # Common LLM config attributes
            if hasattr(config, 'model_name') and config.model_name:
                config_items.append(("Model", config.model_name))
            if hasattr(config, 'provider') and config.provider:
                config_items.append(("Provider", config.provider))
            if hasattr(config, 'temperature') and config.temperature is not None:
                config_items.append(("Temperature", config.temperature))
            if hasattr(config, 'max_tokens') and config.max_tokens:
                config_items.append(("Max Tokens", config.max_tokens))
            if hasattr(config, 'api_base') and config.api_base:
                config_items.append(("API Base", config.api_base))
            
            # Display formatted config items
            if config_items:
                for key, value in config_items:
                    print(f"  {key:12}: {value}")
            else:
                # Fallback to string representation if no known attributes
                print(f"  {config}")
            
            print("=" * 40 + "\n")
    
    def print_workspace_info(self, workspace_path: str) -> None:
        """Print workspace information."""
        if not self.minimal:
            print(f"\n📂 Workspace")
            print("-" * 15)
            print(f"  Path: {workspace_path}")
            print("-" * 15)