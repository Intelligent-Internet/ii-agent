"""Pytest configuration and fixtures for ii-agent tests."""

import pytest
import asyncio
import tempfile
import uuid
import vcr
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from typing import Generator

from ii_agent.core.event import RealtimeEvent, EventType
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.controller.state import State
from ii_agent.utils.workspace_manager import WorkspaceManager


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_logger():
    """Mock logger for tests."""
    return Mock()


@pytest.fixture
def event_stream(mock_logger):
    """Create an AsyncEventStream for testing."""
    return AsyncEventStream(logger=mock_logger)


@pytest.fixture
def sample_event():
    """Create a sample RealtimeEvent for testing."""
    return RealtimeEvent(
        type=EventType.AGENT_RESPONSE, content={"text": "test message"}
    )


@pytest.fixture
def mock_workspace_manager(temp_dir):
    """Create a mock WorkspaceManager."""
    manager = Mock(spec=WorkspaceManager)
    manager.root = str(temp_dir)
    manager.workspace_path.return_value = temp_dir
    manager.relative_path.return_value = "test_file.txt"
    return manager


@pytest.fixture
def empty_state():
    """Create an empty State for testing."""
    return State()


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = Mock()
    client.generate = AsyncMock()
    return client


@pytest.fixture
def mock_tool():
    """Create a mock tool."""
    tool = Mock()
    tool.name = "test_tool"
    tool.execute = AsyncMock()
    tool.should_confirm_execute = AsyncMock(return_value=None)
    return tool


@pytest.fixture
def session_id():
    """Generate a test session ID."""
    return uuid.uuid4()


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def vcr_config():
    """Configuration for VCR cassettes."""
    return {
        "record_mode": "once",
        "match_on": ["method", "uri"],
        "filter_headers": ["authorization", "x-api-key"],
        "serializer": "json",
    }


@pytest.fixture
def vcr_cassette_dir():
    """Base directory for VCR cassettes."""
    return Path(__file__).parent / "cassettes"


@pytest.fixture
def web_visit_vcr(vcr_cassette_dir, vcr_config):
    """VCR instance for web visit client tests."""
    cassette_dir = vcr_cassette_dir / "web_visit"
    cassette_dir.mkdir(parents=True, exist_ok=True)

    return vcr.VCR(cassette_library_dir=str(cassette_dir), **vcr_config)


@pytest.fixture
def web_search_vcr(vcr_cassette_dir, vcr_config):
    """VCR instance for web search client tests."""
    cassette_dir = vcr_cassette_dir / "web_search"
    cassette_dir.mkdir(parents=True, exist_ok=True)

    return vcr.VCR(cassette_library_dir=str(cassette_dir), **vcr_config)
