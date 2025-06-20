from ii_agent.core.config.ii_agent_config import IIAgentConfig


def load_ii_agent_config() -> IIAgentConfig:
    """Load the IIAgent config from the environment variables."""
    return IIAgentConfig()
