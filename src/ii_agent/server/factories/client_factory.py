from ii_agent.llm.base import LLMClient
from ii_agent.llm import get_client


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
        else:
            raise ValueError(f"Unknown model name: {model_name}")
