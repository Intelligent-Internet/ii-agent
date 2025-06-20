from ii_agent.llm.base import (
    LLMClient, 
    LLMMessages, 
    AssistantContentBlock, 
    UserContentBlock, 
    TextPrompt, 
    ToolFormattedResult,
    ToolParam
)
from ii_agent.llm import get_client
import os
from typing import Any, Tuple


class OpenRouterClientWrapper(LLMClient):
    """Wrapper for OpenRouter client to handle multi-entry messages."""
    
    def __init__(self, openrouter_client: LLMClient):
        """Initialize with the actual OpenRouter client."""
        self.client = openrouter_client
    
    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int | None = None,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses, converting multi-entry messages to single-entry."""
        
        # Convert multi-entry messages to single-entry messages
        converted_messages = []
        
        for message_list in messages:
            if len(message_list) == 1:
                # Single entry, keep as-is
                converted_messages.append(message_list)
            else:
                # Multiple entries, need to split or merge
                user_messages = []
                assistant_messages = []
                
                for message in message_list:
                    if isinstance(message, UserContentBlock):
                        user_messages.append(message)
                    else:
                        assistant_messages.append(message)
                
                # Add user messages first (if any)
                if user_messages:
                    if len(user_messages) == 1:
                        converted_messages.append(user_messages)
                    else:
                        # Multiple user messages, combine text content
                        combined_text_parts = []
                        for msg in user_messages:
                            if isinstance(msg, TextPrompt):
                                combined_text_parts.append(msg.text)
                            elif isinstance(msg, ToolFormattedResult):
                                result_text = f"Tool Result ({msg.tool_name}): {msg.tool_output}"
                                combined_text_parts.append(result_text)
                        
                        if combined_text_parts:
                            combined_text = "\n\n".join(combined_text_parts)
                            converted_messages.append([TextPrompt(text=combined_text)])
                
                # Add assistant messages (if any)
                if assistant_messages:
                    for msg in assistant_messages:
                        converted_messages.append([msg])
        
        # Call the actual OpenRouter client with converted messages
        return self.client.generate(
            messages=converted_messages,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            thinking_tokens=thinking_tokens,
        )


class ClientFactory:
    """Factory for creating LLM clients based on model configuration."""

    def __init__(self, project_id: str = None, region: str = None):
        """Initialize the client factory with configuration.

        Args:
            project_id: Project ID for cloud services
            region: Region for cloud services
        """
        self.project_id = project_id
        self.region = region

    def create_client(self, model_name: str, **kwargs) -> LLMClient:
        """Create an LLM client based on the model name and configuration.

        Args:
            model_name: The name of the model to use
            **kwargs: Additional configuration options like thinking_tokens

        Returns:
            LLMClient: Configured LLM client instance

        Raises:
            ValueError: If the model name is not supported
        """
        # If OPENROUTER_API_KEY is available, use OpenRouter for all models with wrapper
        if os.getenv("OPENROUTER_API_KEY"):
            return get_client(
                "openrouter",
                model_name=model_name,
            )
        
        # Otherwise use provider-specific logic
        if "claude" in model_name:
            return get_client(
                "anthropic-direct",
                model_name=model_name,
                use_caching=False,
                project_id=self.project_id,
                region=self.region,
                thinking_tokens=kwargs.get("thinking_tokens", 0),
            )
        elif "gemini" in model_name:
            return get_client(
                "gemini-direct",
                model_name=model_name,
                project_id=self.project_id,
                region=self.region,
            )
        elif model_name in ["o3", "o4-mini", "gpt-4.1", "gpt-4o"]:
            return get_client(
                "openai-direct",
                model_name=model_name,
                azure_model=kwargs.get("azure_model", True),
                cot_model=kwargs.get("cot_model", False),
            )
        else:
            raise ValueError(f"Unknown model name: {model_name}")
