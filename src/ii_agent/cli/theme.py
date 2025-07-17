"""
Theme system for CLI visualization.

This module provides a consistent theming system similar to anon-kode-main
for professional CLI appearance.
"""

from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum


class ThemeType(Enum):
    """Available theme types."""
    LIGHT = "light"
    DARK = "dark"
    LIGHT_DALTONIZED = "light-daltonized"
    DARK_DALTONIZED = "dark-daltonized"


@dataclass
class DiffColors:
    """Color scheme for diff visualization."""
    added: str
    removed: str
    added_dimmed: str
    removed_dimmed: str


@dataclass
class Theme:
    """Theme configuration for CLI."""
    # Core colors
    bash_border: str
    claude: str
    permission: str
    secondary_border: str
    text: str
    secondary_text: str
    suggestion: str
    
    # Semantic colors
    success: str
    error: str
    warning: str
    diff: DiffColors
    
    # Rich style mappings
    @property
    def styles(self) -> Dict[str, str]:
        """Get Rich style mappings."""
        return {
            "claude": self.claude,
            "bash_border": self.bash_border,
            "permission": self.permission,
            "secondary_border": self.secondary_border,
            "text": self.text,
            "secondary_text": self.secondary_text,
            "suggestion": self.suggestion,
            "success": self.success,
            "error": self.error,
            "warning": self.warning,
            "diff.added": self.diff.added,
            "diff.removed": self.diff.removed,
            "diff.added_dimmed": self.diff.added_dimmed,
            "diff.removed_dimmed": self.diff.removed_dimmed,
        }


# Theme definitions
LIGHT_THEME = Theme(
    bash_border="#ff0087",
    claude="#5f97cd",
    permission="#5769f7",
    secondary_border="#999",
    text="#000",
    secondary_text="#666",
    suggestion="#5769f7",
    success="#2c7a39",
    error="#ab2b3f",
    warning="#966c1e",
    diff=DiffColors(
        added="#69db7c",
        removed="#ffa8b4",
        added_dimmed="#c7e1cb",
        removed_dimmed="#fdd2d8"
    )
)

LIGHT_DALTONIZED_THEME = Theme(
    bash_border="#0066cc",
    claude="#5f97cd",
    permission="#3366ff",
    secondary_border="#999",
    text="#000",
    secondary_text="#666",
    suggestion="#3366ff",
    success="#006699",
    error="#cc0000",
    warning="#ff9900",
    diff=DiffColors(
        added="#99ccff",
        removed="#ffcccc",
        added_dimmed="#d1e7fd",
        removed_dimmed="#ffe9e9"
    )
)

DARK_THEME = Theme(
    bash_border="#fd5db1",
    claude="#5f97cd",
    permission="#b1b9f9",
    secondary_border="#888",
    text="#fff",
    secondary_text="#999",
    suggestion="#b1b9f9",
    success="#4eba65",
    error="#ff6b80",
    warning="#ffc107",
    diff=DiffColors(
        added="#225c2b",
        removed="#7a2936",
        added_dimmed="#47584a",
        removed_dimmed="#69484d"
    )
)

DARK_DALTONIZED_THEME = Theme(
    bash_border="#3399ff",
    claude="#5f97cd",
    permission="#99ccff",
    secondary_border="#888",
    text="#fff",
    secondary_text="#999",
    suggestion="#99ccff",
    success="#3399ff",
    error="#ff6666",
    warning="#ffcc00",
    diff=DiffColors(
        added="#004466",
        removed="#660000",
        added_dimmed="#3e515b",
        removed_dimmed="#3e2c2c"
    )
)

# Theme registry
THEMES = {
    ThemeType.LIGHT: LIGHT_THEME,
    ThemeType.LIGHT_DALTONIZED: LIGHT_DALTONIZED_THEME,
    ThemeType.DARK: DARK_THEME,
    ThemeType.DARK_DALTONIZED: DARK_DALTONIZED_THEME,
}


def get_theme(theme_type: Optional[ThemeType] = None) -> Theme:
    """Get theme by type, defaulting to dark theme."""
    if theme_type is None:
        theme_type = ThemeType.DARK
    
    return THEMES.get(theme_type, DARK_THEME)


def get_current_theme() -> Theme:
    """Get the current theme (can be extended to read from config)."""
    return get_theme(ThemeType.DARK)