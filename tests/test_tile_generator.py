"""Tests for TileGenerator breadcrumb placement and tile generation."""

import asyncio
from pathlib import Path
from ii_agent.storage.tile_generator import TileGenerator
from ii_agent.storage.slab_checkpoint import SlabCheckpoint
from ii_agent.llm.base import TextPrompt


class DummyMemvid:
    def __init__(self, dir):
        self.video_dir = dir
    def write(self, content, path, content_type=None):
        # Simulate write; accept BytesIO
        try:
            _ = content.read()
        except Exception:
            pass


async def test_generate_tile_breadcrumb_placement(tmp_path):
    # Setup checkpoint system with dummy memvid
    cp = SlabCheckpoint()
    cp.memvid = DummyMemvid(str(tmp_path))
    tg = TileGenerator(checkpoint_system=cp)

    # Create a fake todo
    todo = {"id": "1", "content": "Fix authentication bug in auth.ts and jwt.ts", "status": "pending"}

    # Create minimal message list
    message_lists = [[TextPrompt(text="Please fix auth.ts and jwt.ts for JWT bug")]]

    tile = await tg._generate_tile_for_todo(todo, message_lists, microkernel={"important_breadcrumbs": ["auth.ts", "jwt.ts"]}, parent_slab_id="slab_0")

    assert "breadcrumb_placement" in tile["compressed_context"]
    assert isinstance(tile["compressed_context"]["breadcrumb_placement"], dict)
