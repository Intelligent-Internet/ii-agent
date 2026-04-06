"""
FastAPI router for testing call_agent / call_agent_stream.

Usage:
    # Start server:
    python -m ii_agent.ii_claw.run

    # POST /ii_claw/run  (blocking, returns full result)
    curl -X POST http://localhost:8686/ii_claw/run \
      -H "Content-Type: application/json" \
      -d '{"text": "What are AI agent trends?", "agent_type": "general"}'

    # POST /ii_claw/stream  (SSE, streams events)
    curl -N http://localhost:8686/ii_claw/stream \
      -H "Content-Type: application/json" \
      -d '{"text": "What are AI agent trends?", "agent_type": "fast_research"}'
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ii_agent.agents.types import AgentType
from ii_agent.ii_claw.call_agent import (
    CallAgentInput,
    CallAgentOutput,
    call_agent,
    call_agent_stream,
)

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """Request body for /ii_claw/run and /ii_claw/stream."""

    text: str
    user_id: str = "cli-user"
    model_id: Optional[str] = None
    source: str = "system"  # "user" | "system"
    agent_type: str = "general"
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    file_ids: List[str] = Field(default_factory=list)
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    github_repository: Optional[Dict[str, str]] = None

    def to_call_input(self) -> CallAgentInput:
        return CallAgentInput(
            user_id=self.user_id,
            text=self.text,
            model_id=self.model_id,
            source=self.source,
            agent_type=AgentType(self.agent_type),
            tool_args=self.tool_args,
            file_ids=self.file_ids,
            session_id=self.session_id,
            metadata=self.metadata,
            github_repository=self.github_repository,
        )


class FileAttachmentResponse(BaseModel):
    """A file delivered to the user."""
    name: str
    url: str
    file_type: str = "documents"


class MediaResponse(BaseModel):
    """All media/files produced by the agent."""
    images: List[Dict[str, Any]] = Field(default_factory=list)
    videos: List[Dict[str, Any]] = Field(default_factory=list)
    audio: List[Dict[str, Any]] = Field(default_factory=list)
    files: List[FileAttachmentResponse] = Field(default_factory=list)


class AgentResponse(BaseModel):
    """Response body for /ii_claw/run."""

    session_id: str
    run_id: str
    status: str
    content: Optional[str] = None
    media: MediaResponse = Field(default_factory=MediaResponse)
    events_count: int = 0
    events: List[dict] = Field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# FastAPI app + router
# ---------------------------------------------------------------------------

app = FastAPI(title="II-Claw Agent Test Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _output_to_response(output: CallAgentOutput) -> AgentResponse:
    """Convert CallAgentOutput to JSON-serializable response."""
    media = MediaResponse()
    if output.media:
        media = MediaResponse(
            images=output.media.images,
            videos=output.media.videos,
            audio=output.media.audio,
            files=[
                FileAttachmentResponse(name=f.name, url=f.url, file_type=f.file_type)
                for f in output.media.files
            ],
        )

    return AgentResponse(
        session_id=output.session_id,
        run_id=output.run_id,
        status=output.status.value if output.status else "unknown",
        content=output.content,
        media=media,
        events_count=len(output.events),
        events=[e.model_dump(mode="json") for e in output.events],
        error=output.error,
    )


@app.post("/ii_claw/run", response_model=AgentResponse)
async def run_agent(req: AgentRequest):
    """Run agent (blocking), return full result with all events."""
    inp = req.to_call_input()
    output = await call_agent(inp)

    if output.error:
        return JSONResponse(
            status_code=500,
            content=_output_to_response(output).model_dump(mode="json"),
        )

    return _output_to_response(output)


@app.post("/ii_claw/stream")
async def stream_agent(req: AgentRequest):
    """Run agent with SSE streaming. Each event is an AppEvent JSON."""
    inp = req.to_call_input()

    async def event_generator():
        async for event in call_agent_stream(inp):
            data = event.model_dump(mode="json")
            yield {
                "event": getattr(event, "name", "message"),
                "data": json.dumps(data, default=str),
            }

    return EventSourceResponse(event_generator())


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "ii_agent.ii_claw.run:app",
        host="0.0.0.0",
        port=8686,
        reload=False,
    )
