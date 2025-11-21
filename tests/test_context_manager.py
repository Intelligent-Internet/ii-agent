"""Tests for ContextWindowManager model-aware reduction and harmonic miss integration."""

from types import SimpleNamespace
from ii_agent.server.chat.models import MessageRole
from pathlib import Path
import tempfile
import os

from ii_agent.server.chat.context_manager import ContextWindowManager
from ii_agent.server.chat.harmonic_miss_tracker import HarmonicMissTracker
from ii_agent.llm.model_constants import CONTEXT_WINDOWS


def make_messages(num, tokens_per, roles=None):
    # Use MessageRole enum for compatibility with reduce_message_tokens
    roles = roles or ([MessageRole.USER, MessageRole.ASSISTANT] * (num // 2 + 1))
    msgs = []
    for i in range(num):
        role = roles[i]
        msgs.append(SimpleNamespace(role=role, tokens=tokens_per))
    return msgs


def test_reduce_message_tokens_model_awareness():
    cm = ContextWindowManager
    model_id = 'gpt-4o'
    context_window = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS['default'])
    # Create messages to total > 90% of context
    tokens_per = 10_000
    num_msgs = int((context_window * 0.95) // tokens_per)

    messages = make_messages(num_msgs, tokens_per)
    total_before = sum(m.tokens for m in messages)
    assert total_before > context_window * 0.9

    reduced = cm.reduce_message_tokens(messages, model_id=model_id)
    total_after = sum(m.tokens for m in reduced)
    assert total_after < context_window * 0.9
    assert len(reduced) <= len(messages)


def test_harmonic_miss_tracker_basic(tmp_path):
    # Use a temp file for persistence
    storage_file = Path(tempfile.gettempdir()) / f"harmonic_{os.getpid()}.json"
    if storage_file.exists():
        storage_file.unlink()
    tracker = HarmonicMissTracker(storage_path=str(storage_file))
    model_id = 'gpt-4o'
    cw = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS['default'])

    # Simulate many errors at high pressure
    for i in range(20):
        tracker.track(model_id, 'hallucination', context_tokens=int(cw * 0.92), context_window=cw, metadata={'test': True})

    stats = tracker.get_stats(model_id)
    assert stats['total_events'] == 20
    assert stats['error_types'].get('hallucination', 0) == 20

    recommended = tracker.recommend_threshold(model_id)
    assert recommended is not None
    assert 0.0 < recommended <= 1.0


def test_context_window_manager_harmonic_integration(tmp_path):
    storage_file = Path(tempfile.gettempdir()) / f"harmonic_cwm_{os.getpid()}.json"
    if storage_file.exists():
        storage_file.unlink()
    tracker = HarmonicMissTracker(storage_path=str(storage_file))
    # Replace ContextWindowManager's tracker with ours so we don't affect real data
    ContextWindowManager._harmonic_miss_tracker = tracker

    model_id = 'gpt-4o'
    cw = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS['default'])

    # Track a few events
    for i in range(5):
        ContextWindowManager.track_harmonic_miss(model_id, 'inconsistency', int(cw * 0.88), metadata={'i': i})

    stats = ContextWindowManager.get_harmonic_miss_stats(model_id)
    assert stats.get('total_errors') == 5
    assert stats.get('error_types', {}).get('inconsistency') == 5


def test_checkpoint_threshold_considers_harmonic_recommendation(tmp_path):
    from ii_agent.server.chat.context_manager import ContextWindowManager
    from ii_agent.llm.model_constants import CONTEXT_WINDOWS

    storage_file = Path(tempfile.gettempdir()) / f"harmonic_chk_{os.getpid()}.json"
    if storage_file.exists():
        storage_file.unlink()

    tracker = HarmonicMissTracker(storage_path=str(storage_file))
    ContextWindowManager._harmonic_miss_tracker = tracker
    model_id = 'gpt-4o'
    cw = CONTEXT_WINDOWS.get(model_id)

    # Inject many high-pressure events to cause a recommended threshold
    for i in range(20):
        tracker.track(model_id, 'edit_slip', int(cw * 0.96), cw)

    recommended = tracker.recommend_threshold(model_id)
    assert recommended is not None

    threshold = ContextWindowManager.get_checkpoint_threshold_for_model(model_id)
    # The returned threshold should be <= recommended (safer)
    assert threshold <= recommended
