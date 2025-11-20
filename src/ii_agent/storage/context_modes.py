"""Context modes - suspend, high detail, high capacity."""

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass


class ContextMode(Enum):
    """Context operation modes."""

    NORMAL = "normal"              # Standard context window
    SUSPENDED = "suspended"        # Context checkpointed, operating on microkernel
    HIGH_DETAIL = "high_detail"    # Deep dive on specific aspect (expanded context)
    HIGH_CAPACITY = "high_capacity"  # Empty context for pure thinking


@dataclass
class ContextState:
    """Current context state and mode."""

    mode: ContextMode
    active_slab_id: Optional[str] = None
    microkernel: Optional[Dict] = None
    detail_focus: Optional[str] = None  # What we're deep diving on
    capacity_tokens: int = 0  # Current token usage

    def suspend(self, slab_id: str, microkernel: Dict):
        """Suspend context to checkpoint."""
        self.mode = ContextMode.SUSPENDED
        self.active_slab_id = slab_id
        self.microkernel = microkernel

    def enter_high_detail(self, focus: str):
        """Enter high detail mode for specific focus."""
        self.mode = ContextMode.HIGH_DETAIL
        self.detail_focus = focus

    def enter_high_capacity(self, tokens: int):
        """Enter high capacity thinking mode."""
        self.mode = ContextMode.HIGH_CAPACITY
        self.capacity_tokens = tokens

    def resume_normal(self):
        """Resume normal operation."""
        self.mode = ContextMode.NORMAL
        self.active_slab_id = None
        self.detail_focus = None
        self.capacity_tokens = 0

    def get_status(self) -> str:
        """Get human-readable status."""
        if self.mode == ContextMode.NORMAL:
            return "Normal operation"
        elif self.mode == ContextMode.SUSPENDED:
            return f"Suspended (checkpoint: {self.active_slab_id})"
        elif self.mode == ContextMode.HIGH_DETAIL:
            return f"High detail mode (focus: {self.detail_focus})"
        elif self.mode == ContextMode.HIGH_CAPACITY:
            return f"High capacity thinking ({self.capacity_tokens:,} tokens)"
        return "Unknown mode"


class ContextModeManager:
    """Manages context mode transitions."""

    def __init__(self):
        self.state = ContextState(mode=ContextMode.NORMAL)

    def transition_to_suspended(
        self,
        slab_id: str,
        microkernel: Dict
    ) -> str:
        """
        Transition to suspended mode.

        Workflow:
        1. Checkpoint current context to slab
        2. Extract microkernel (tasks, goals, activity)
        3. Enter suspended mode with microkernel

        Returns:
            Status message
        """
        self.state.suspend(slab_id, microkernel)

        return (
            f"Context suspended to {slab_id}\n"
            f"Microkernel active:\n"
            f"  - Tasks: {len(microkernel.get('tasks', []))}\n"
            f"  - Goals: {len(microkernel.get('goals', []))}\n"
            f"  - Current activity: {len(microkernel.get('current_activity', []))}\n"
            f"  - Breadcrumbs: {len(microkernel.get('important_breadcrumbs', []))}"
        )

    def transition_to_high_detail(self, focus: str) -> str:
        """
        Transition to high detail mode.

        Allows deep dive on specific aspect while suspended.

        Args:
            focus: What to focus on (e.g., "OAuth implementation", "test failures")

        Returns:
            Status message
        """
        self.state.enter_high_detail(focus)

        return (
            f"Entered high detail mode\n"
            f"Focus: {focus}\n"
            f"Use RecallContext or MicrocontextSubroutine to expand detail"
        )

    def transition_to_high_capacity(self, tokens: int = 0) -> str:
        """
        Transition to high capacity thinking mode.

        Creates EMPTY context space for pure thinking - no historical baggage.
        Model starts with only microkernel, no detailed context.

        Args:
            tokens: Available token capacity (default: 0 = maximum available)

        Returns:
            Status message
        """
        self.state.enter_high_capacity(tokens)

        return (
            f"Entered high capacity thinking mode\n"
            f"Context: EMPTY (as minimal as possible)\n"
            f"Available for pure thinking with microkernel only\n"
            f"Mode will return to normal after thinking completes"
        )

    def return_to_normal(self) -> str:
        """Return to normal mode from any other mode."""
        prev_mode = self.state.mode
        self.state.resume_normal()

        return f"Returned to normal mode from {prev_mode.value}"

    def get_mode_guidance(self) -> str:
        """Get guidance for current mode."""
        if self.state.mode == ContextMode.SUSPENDED:
            return (
                "Context is suspended. Current microkernel:\n"
                f"Tasks: {self.state.microkernel.get('tasks', [])}\n"
                f"Goals: {self.state.microkernel.get('goals', [])}\n"
                f"Breadcrumbs: {self.state.microkernel.get('important_breadcrumbs', [])}\n\n"
                "To continue work:\n"
                "- Use RecallContext to query breadcrumbs\n"
                "- Use MicrocontextSubroutine to expand detail\n"
                "- Enter high detail mode for focused work\n"
                "- Enter high capacity mode for deep thinking"
            )
        elif self.state.mode == ContextMode.HIGH_DETAIL:
            return (
                f"In high detail mode (focus: {self.state.detail_focus})\n"
                "Operating with expanded context for this focus.\n"
                "Return to normal when detail work complete."
            )
        elif self.state.mode == ContextMode.HIGH_CAPACITY:
            return (
                f"In high capacity thinking mode (EMPTY context)\n"
                "Context is minimal - only microkernel present.\n"
                "Use this mode for pure reasoning without historical context weight.\n"
                "Return to normal after thinking completes."
            )
        else:
            return "Normal operation mode"
