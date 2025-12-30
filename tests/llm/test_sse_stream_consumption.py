"""Unit tests for SSE stream consumption in OpenAI LLM provider.

This module tests the SSE (Server-Sent Events) stream consumption logic
that was added to handle gemini-cli-openai worker which returns SSE format
by default even for non-streaming requests.

Tests:
- Multi-chunk content aggregation
- Tool call aggregation from stream chunks
- Finish reason detection
- list+join performance pattern
"""

import pytest
from unittest.mock import MagicMock
from typing import List, Any, Optional


class MockDelta:
    """Mock OpenAI delta object."""
    def __init__(self, content: Optional[str] = None, tool_calls: Optional[List] = None):
        self.content = content
        self.tool_calls = tool_calls or []


class MockChoice:
    """Mock OpenAI choice object."""
    def __init__(self, delta: Optional[MockDelta] = None, finish_reason: Optional[str] = None):
        self.delta = delta or MockDelta()
        self.finish_reason = finish_reason
        self.index = 0


class MockChunk:
    """Mock OpenAI stream chunk."""
    def __init__(self, choices: Optional[List[MockChoice]] = None):
        self.choices = choices or []


class MockStream:
    """Mock async iterator for OpenAI stream."""
    
    def __init__(self, chunks: List[Any]):
        self.chunks = chunks
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        return self.chunks.pop(0)


async def consume_stream_to_content(stream: MockStream) -> str:
    """
    Simulates the stream consumption logic from openai.py agenerate().
    
    This is the exact pattern used in the production code for O(n) performance.
    """
    content_chunks = []
    
    async for chunk in stream:
        if chunk.choices:
            choice = chunk.choices[0]
            if hasattr(choice.delta, 'content') and choice.delta.content:
                content_chunks.append(choice.delta.content)
    
    return ''.join(content_chunks)


async def consume_stream_with_tools(stream: MockStream):
    """
    Simulates stream consumption with tool calls.
    
    Returns tuple of (content, tool_calls, finish_reason).
    """
    content_chunks = []
    collected_tool_calls = []
    finish_reason = None
    
    async for chunk in stream:
        if chunk.choices:
            choice = chunk.choices[0]
            if hasattr(choice.delta, 'content') and choice.delta.content:
                content_chunks.append(choice.delta.content)
            if hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
                for tc in choice.delta.tool_calls:
                    collected_tool_calls.append(tc)
            if hasattr(choice, 'finish_reason') and choice.finish_reason:
                finish_reason = choice.finish_reason
    
    return (''.join(content_chunks), collected_tool_calls, finish_reason)


class TestSSEStreamConsumption:
    """Tests for SSE stream consumption logic."""
    
    @pytest.mark.asyncio
    async def test_single_chunk_content(self):
        """Test consumption of a single content chunk."""
        chunks = [
            MockChunk([MockChoice(MockDelta("Hello, world!"))])
        ]
        stream = MockStream(chunks)
        
        result = await consume_stream_to_content(stream)
        assert result == "Hello, world!"
    
    @pytest.mark.asyncio
    async def test_multi_chunk_content(self):
        """Test aggregation of multiple content chunks."""
        chunks = [
            MockChunk([MockChoice(MockDelta("Hello, "))]),
            MockChunk([MockChoice(MockDelta("world!"))]),
            MockChunk([MockChoice(MockDelta(" How are you?"))]),
        ]
        stream = MockStream(chunks)
        
        result = await consume_stream_to_content(stream)
        assert result == "Hello, world! How are you?"
    
    @pytest.mark.asyncio
    async def test_empty_chunks(self):
        """Test handling of empty chunks (no content)."""
        chunks = [
            MockChunk([MockChoice(MockDelta())]),
            MockChunk([MockChoice(MockDelta("Actual content"))]),
            MockChunk([MockChoice(MockDelta())]),
        ]
        stream = MockStream(chunks)
        
        result = await consume_stream_to_content(stream)
        assert result == "Actual content"
    
    @pytest.mark.asyncio
    async def test_multi_chunk_with_finish_reason(self):
        """Test that finish_reason is captured from the last chunk."""
        chunks = [
            MockChunk([MockChoice(MockDelta("Step 1: "))]),
            MockChunk([MockChoice(MockDelta("Learn Python basics"))]),
            MockChunk([MockChoice(None, finish_reason="stop")]),
        ]
        stream = MockStream(chunks)
        
        content, tool_calls, finish_reason = await consume_stream_with_tools(stream)
        assert content == "Step 1: Learn Python basics"
        assert finish_reason == "stop"
        assert tool_calls == []
    
    @pytest.mark.asyncio
    async def test_tool_call_aggregation(self):
        """Test that tool calls are aggregated from stream chunks."""
        mock_tool_1 = MagicMock()
        mock_tool_1.id = "call_1"
        mock_tool_1.type = "function"
        
        mock_tool_2 = MagicMock()
        mock_tool_2.id = "call_2"
        mock_tool_2.type = "function"
        
        chunks = [
            MockChunk([MockChoice(MockDelta("I'll help you"))]),
            MockChunk([MockChoice(MockDelta(" with that"))]),
            MockChunk([MockChoice()]),
        ]
        chunks[2].choices[0].delta.tool_calls = [mock_tool_1, mock_tool_2]
        
        stream = MockStream(chunks)
        
        content, tool_calls, finish_reason = await consume_stream_with_tools(stream)
        assert content == "I'll help you with that"
        assert len(tool_calls) == 2
        assert tool_calls[0].id == "call_1"
        assert tool_calls[1].id == "call_2"
    
    @pytest.mark.asyncio
    async def test_list_join_performance_pattern(self):
        """Test that list+join produces correct result (O(n) pattern)."""
        chunks = [MockChunk([MockChoice(MockDelta(f"chunk_{i} "))]) for i in range(100)]
        stream = MockStream(chunks)
        
        result = await consume_stream_to_content(stream)
        
        expected = " ".join([f"chunk_{i}" for i in range(100)]) + " "
        assert result == expected
        assert result.count("  ") == 0
    
    @pytest.mark.asyncio
    async def test_empty_stream(self):
        """Test handling of completely empty stream."""
        stream = MockStream([])
        
        result = await consume_stream_to_content(stream)
        assert result == ""
