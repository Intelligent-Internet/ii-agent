"""Credits and subscription configuration."""

from typing import Dict
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CreditsSettings(BaseSettings):
    """Credits and subscription plan configuration.

    Environment variables use CREDITS_ prefix:
        CREDITS_DEFAULT_USER_CREDITS: Default credits for new users
        CREDITS_DEFAULT_SUBSCRIPTION_PLAN: Default plan for new users
        CREDITS_BETA_PROGRAM_ENABLED: Enable beta program bonus credits
        CREDITS_BETA_PROGRAM_BONUS_CREDITS: Bonus credits for beta users
        CREDITS_WAITLIST_ENABLED: Enable waitlist program

    Example .env:
        CREDITS_DEFAULT_USER_CREDITS=300.0
        CREDITS_DEFAULT_SUBSCRIPTION_PLAN=free
        CREDITS_BETA_PROGRAM_ENABLED=true
        CREDITS_BETA_PROGRAM_BONUS_CREDITS=2000.0
    """

    model_config = SettingsConfigDict(
        env_prefix="CREDITS_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Global billing toggle — set CREDITS_BILLING_ENABLED=false to disable
    # all credit deductions.  Useful for self-hosted / local deployments
    # where the operator pays directly for their own API keys.
    billing_enabled: bool = Field(
        default=True,
        description=(
            "Master toggle for credit billing.  When False, no credits are "
            "deducted for any LLM or tool usage regardless of config_type."
        ),
    )

    # Default credits for new users
    default_user_credits: float = Field(
        default=300.0,
        description="Default credits allocated to new users upon registration",
        ge=0.0,
    )

    # Default subscription plan
    default_subscription_plan: str = Field(
        default="free",
        description="Default subscription plan for new users",
    )

    # Credits allocation per plan
    default_plans_credits: Dict[str, float] = Field(
        default_factory=lambda: {
            "free": 300.0,
            "plus": 2000.0,
            "pro": 10000.0,
        },
        description="Credit allocation for each subscription plan",
    )

    # Beta program configuration
    beta_program_enabled: bool = Field(
        default=True,
        description="Enable beta program to grant bonus credits on login",
    )

    beta_program_bonus_credits: float = Field(
        default=2000.0,
        description="Bonus credits granted to beta program participants",
        ge=0.0,
    )

    # Waitlist configuration
    waitlist_enabled: bool = Field(
        default=False,
        description="Enable waitlist program for gating access",
    )

    def get_plan_credits(self, plan: str) -> float:
        """Get credit allocation for a subscription plan.

        Args:
            plan: Plan name ('free', 'plus', 'pro')

        Returns:
            float: Credit amount for the plan, or default if plan not found
        """
        return self.default_plans_credits.get(plan.lower(), self.default_user_credits)

    def should_grant_beta_bonus(self) -> bool:
        """Check if beta bonus credits should be granted.

        Returns:
            bool: True if beta program is enabled
        """
        return self.beta_program_enabled and self.beta_program_bonus_credits > 0
