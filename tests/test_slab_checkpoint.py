"""Tests for SlabCheckpoint persistence and metadata."""

import asyncio
from pathlib import Path
from ii_agent.storage.slab_checkpoint import SlabCheckpoint
from ii_agent.llm.base import TextPrompt, TextResult


async def test_slab_checkpoint_metadata_persistence(tmp_path):
    memvid_dir = tmp_path / "memvid"
    memvid_dir.mkdir(parents=True, exist_ok=True)

    cp = SlabCheckpoint(checkpoint_dir=str(memvid_dir))

    message_lists = [[TextPrompt(text="Hello world")], [TextResult(text="Reply")]]

    slab_id = await cp.create_checkpoint(message_lists)

    # Metadata file should include the slab id
    metadata_path = memvid_dir / "checkpoint_metadata.json"
    assert metadata_path.exists()
    content = metadata_path.read_text()
    assert slab_id in content
