"""Unit tests for ii_tool.browser.models module.

This module tests the Pydantic models used for browser interactions:
- TabInfo: Browser tab representation
- Coordinates: Position/dimension information
- Rect: Rectangle with bounds
- InteractiveElement: Clickable/interactive page elements
- BrowserError and URLNotAllowedError: Exception classes
- Viewport: Browser viewport state
"""

import pytest
from pydantic import ValidationError


from ii_tool.browser.models import (
    TabInfo,
    Coordinates,
    Rect,
    InteractiveElement,
    BrowserError,
    URLNotAllowedError,
    Viewport,
)


# =============================================================================
# TabInfo Tests
# =============================================================================

class TestTabInfo:
    """Tests for TabInfo model."""

    def test_all_fields_required(self):
        """TabInfo requires page_id, url, and title."""
        tab = TabInfo(page_id=1, url="https://example.com", title="Example")
        assert tab.page_id == 1
        assert tab.url == "https://example.com"
        assert tab.title == "Example"

    def test_missing_field_raises(self):
        """Missing required field raises ValidationError."""
        with pytest.raises(ValidationError):
            TabInfo(page_id=1, url="https://example.com")  # missing title

    def test_page_id_is_int(self):
        """page_id must be an integer."""
        tab = TabInfo(page_id=42, url="https://test.com", title="Test")
        assert isinstance(tab.page_id, int)

    def test_serialization(self):
        """TabInfo serializes to dict correctly."""
        tab = TabInfo(page_id=1, url="https://example.com", title="Example")
        data = tab.model_dump()
        assert data == {"page_id": 1, "url": "https://example.com", "title": "Example"}


# =============================================================================
# Coordinates Tests
# =============================================================================

class TestCoordinates:
    """Tests for Coordinates model."""

    def test_required_fields(self):
        """Coordinates requires x and y."""
        coords = Coordinates(x=100, y=200)
        assert coords.x == 100
        assert coords.y == 200

    def test_optional_dimensions(self):
        """width and height are optional."""
        coords = Coordinates(x=100, y=200)
        assert coords.width is None
        assert coords.height is None

    def test_with_dimensions(self):
        """width and height can be provided."""
        coords = Coordinates(x=100, y=200, width=50, height=30)
        assert coords.width == 50
        assert coords.height == 30

    def test_negative_coordinates_allowed(self):
        """Negative coordinates are valid."""
        coords = Coordinates(x=-10, y=-20)
        assert coords.x == -10
        assert coords.y == -20

    def test_zero_coordinates(self):
        """Zero coordinates are valid."""
        coords = Coordinates(x=0, y=0, width=0, height=0)
        assert coords.x == 0
        assert coords.y == 0


# =============================================================================
# Rect Tests
# =============================================================================

class TestRect:
    """Tests for Rect model."""

    def test_all_fields_required(self):
        """Rect requires all boundary and dimension fields."""
        rect = Rect(left=0, top=0, right=100, bottom=50, width=100, height=50)
        assert rect.left == 0
        assert rect.top == 0
        assert rect.right == 100
        assert rect.bottom == 50
        assert rect.width == 100
        assert rect.height == 50

    def test_missing_field_raises(self):
        """Missing required field raises ValidationError."""
        with pytest.raises(ValidationError):
            Rect(left=0, top=0, right=100, bottom=50, width=100)  # missing height

    def test_serialization(self):
        """Rect serializes correctly."""
        rect = Rect(left=10, top=20, right=110, bottom=70, width=100, height=50)
        data = rect.model_dump()
        assert data["left"] == 10
        assert data["width"] == 100


# =============================================================================
# InteractiveElement Tests
# =============================================================================

class TestInteractiveElement:
    """Tests for InteractiveElement model."""

    @pytest.fixture
    def sample_element_data(self):
        """Sample data for creating an InteractiveElement."""
        return {
            "index": 1,
            "tag_name": "button",
            "text": "Click me",
            "attributes": {"class": "btn", "id": "submit-btn"},
            "viewport": {"x": 100, "y": 200},
            "page": {"x": 100, "y": 500},
            "center": {"x": 125, "y": 215},
            "weight": 0.95,
            "browser_agent_id": "element_1",
            "rect": {
                "left": 100,
                "top": 200,
                "right": 150,
                "bottom": 230,
                "width": 50,
                "height": 30,
            },
            "z_index": 10,
        }

    def test_create_from_dict(self, sample_element_data):
        """InteractiveElement can be created from dict."""
        element = InteractiveElement(**sample_element_data)
        assert element.index == 1
        assert element.tag_name == "button"
        assert element.text == "Click me"
        assert element.browser_agent_id == "element_1"

    def test_nested_coordinates(self, sample_element_data):
        """Nested Coordinates objects are parsed correctly."""
        element = InteractiveElement(**sample_element_data)
        assert element.viewport.x == 100
        assert element.viewport.y == 200
        assert element.center.x == 125

    def test_nested_rect(self, sample_element_data):
        """Nested Rect object is parsed correctly."""
        element = InteractiveElement(**sample_element_data)
        assert element.rect.left == 100
        assert element.rect.width == 50

    def test_attributes_dict(self, sample_element_data):
        """attributes is a dict of string key-value pairs."""
        element = InteractiveElement(**sample_element_data)
        assert element.attributes["class"] == "btn"
        assert element.attributes["id"] == "submit-btn"

    def test_input_type_optional(self, sample_element_data):
        """input_type is optional and defaults to None."""
        element = InteractiveElement(**sample_element_data)
        assert element.input_type is None

    def test_input_type_provided(self, sample_element_data):
        """input_type can be provided."""
        sample_element_data["input_type"] = "text"
        element = InteractiveElement(**sample_element_data)
        assert element.input_type == "text"

    def test_camel_case_alias(self, sample_element_data):
        """Model accepts camelCase aliases."""
        camel_data = {
            "index": 1,
            "tagName": "button",
            "text": "Click",
            "attributes": {},
            "viewport": {"x": 0, "y": 0},
            "page": {"x": 0, "y": 0},
            "center": {"x": 0, "y": 0},
            "weight": 0.5,
            "browserAgentId": "elem_1",
            "rect": {"left": 0, "top": 0, "right": 10, "bottom": 10, "width": 10, "height": 10},
            "zIndex": 5,
        }
        element = InteractiveElement(**camel_data)
        assert element.tag_name == "button"
        assert element.browser_agent_id == "elem_1"
        assert element.z_index == 5


# =============================================================================
# BrowserError Tests
# =============================================================================

class TestBrowserError:
    """Tests for BrowserError exception."""

    def test_is_exception(self):
        """BrowserError is an Exception subclass."""
        assert issubclass(BrowserError, Exception)

    def test_can_be_raised(self):
        """BrowserError can be raised and caught."""
        with pytest.raises(BrowserError):
            raise BrowserError("Browser operation failed")

    def test_message(self):
        """BrowserError preserves message."""
        error = BrowserError("Test error message")
        assert str(error) == "Test error message"


# =============================================================================
# URLNotAllowedError Tests
# =============================================================================

class TestURLNotAllowedError:
    """Tests for URLNotAllowedError exception."""

    def test_is_browser_error(self):
        """URLNotAllowedError is a BrowserError subclass."""
        assert issubclass(URLNotAllowedError, BrowserError)

    def test_can_be_raised(self):
        """URLNotAllowedError can be raised and caught."""
        with pytest.raises(URLNotAllowedError):
            raise URLNotAllowedError("URL blocked")

    def test_caught_as_browser_error(self):
        """URLNotAllowedError can be caught as BrowserError."""
        with pytest.raises(BrowserError):
            raise URLNotAllowedError("URL not allowed")


# =============================================================================
# Viewport Tests
# =============================================================================

class TestViewport:
    """Tests for Viewport model."""

    def test_default_values(self):
        """Viewport has sensible defaults."""
        viewport = Viewport()
        assert viewport.width == 1024
        assert viewport.height == 768
        assert viewport.scroll_x == 0
        assert viewport.scroll_y == 0
        assert viewport.device_pixel_ratio == 1.0
        assert viewport.scroll_distance_above_viewport == 0
        assert viewport.scroll_distance_below_viewport == 0

    def test_custom_dimensions(self):
        """Viewport accepts custom dimensions."""
        viewport = Viewport(width=1920, height=1080)
        assert viewport.width == 1920
        assert viewport.height == 1080

    def test_scroll_position(self):
        """Viewport tracks scroll position."""
        viewport = Viewport(scroll_x=100, scroll_y=500)
        assert viewport.scroll_x == 100
        assert viewport.scroll_y == 500

    def test_device_pixel_ratio(self):
        """Viewport supports high DPI displays."""
        viewport = Viewport(device_pixel_ratio=2.0)
        assert viewport.device_pixel_ratio == 2.0

    def test_scroll_distance_tracking(self):
        """Viewport tracks scroll distances."""
        viewport = Viewport(
            scroll_distance_above_viewport=1000,
            scroll_distance_below_viewport=5000,
        )
        assert viewport.scroll_distance_above_viewport == 1000
        assert viewport.scroll_distance_below_viewport == 5000

    def test_camel_case_alias(self):
        """Viewport accepts camelCase aliases."""
        viewport = Viewport(
            scrollX=50,
            scrollY=100,
            devicePixelRatio=1.5,
            scrollDistanceAboveViewport=200,
            scrollDistanceBelowViewport=300,
        )
        assert viewport.scroll_x == 50
        assert viewport.scroll_y == 100
        assert viewport.device_pixel_ratio == 1.5

    def test_serialization(self):
        """Viewport serializes to dict."""
        viewport = Viewport(width=800, height=600)
        data = viewport.model_dump()
        assert "width" in data
        assert data["width"] == 800
