from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


# Pydantic
class TabInfo(BaseModel):
    """Represents information about a browser tab"""

    page_id: int
    url: str
    title: str


class Coordinates(BaseModel):
    x: int
    y: int
    width: Optional[int] = None
    height: Optional[int] = None


class Rect(BaseModel):
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int


class InteractiveElement(BaseModel):
    """Represents an interactive element on the page"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    index: int
    tag_name: str
    text: str
    attributes: dict[str, str]
    viewport: Coordinates
    page: Coordinates
    center: Coordinates
    weight: float
    browser_agent_id: str
    input_type: Optional[str] = field(default=None)
    rect: Rect
    z_index: int


class BrowserError(Exception):
    """Base class for all browser errors"""


class URLNotAllowedError(BrowserError):
    """Error raised when a URL is not allowed"""


class Viewport(BaseModel):
    """Represents the viewport of the browser"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    width: int = field(default_factory=lambda: 1024)
    height: int = field(default_factory=lambda: 768)
    scroll_x: int = field(default_factory=lambda: 0)
    scroll_y: int = field(default_factory=lambda: 0)
    device_pixel_ratio: float = field(default_factory=lambda: 1)
    scroll_distance_above_viewport: int = field(default_factory=lambda: 0)
    scroll_distance_below_viewport: int = field(default_factory=lambda: 0)


class InteractiveElementsData(BaseModel):
    """Represents the data returned by the interactive elements script"""

    viewport: Viewport
    elements: list[InteractiveElement]


@dataclass
class BrowserState:
    url: str
    tabs: list[TabInfo]
    viewport: Viewport = field(default_factory=Viewport)
    screenshot_with_highlights: Optional[str] = None
    screenshot: Optional[str] = None
    interactive_elements: dict[int, InteractiveElement] = field(default_factory=dict)
