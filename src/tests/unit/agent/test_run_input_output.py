"""Unit tests for agents/runs/agent.py RunInput and RunOutput dataclass methods."""

from __future__ import annotations

import uuid
from dataclasses import field
from unittest.mock import MagicMock

import pytest

from ii_agent.agents.runs.agent import (
    RunInput,
    RunOutput,
    RunCancelledEvent,
    SandboxInitializedEvent,
    CustomEvent,
    run_output_event_from_dict,
    RunStartedEvent,
)
from ii_agent.agents.models.message import Message
from ii_agent.tasks.types import RunStatus


# ---------------------------------------------------------------------------
# RunInput.contains_media
# ---------------------------------------------------------------------------

class TestRunInputContainsMedia:
    def test_no_media_returns_false(self):
        ri = RunInput(input_content="hello")
        assert not ri.contains_media()

    def test_with_images_returns_true(self):
        img = MagicMock()
        ri = RunInput(input_content="hello", images=[img])
        assert ri.contains_media()

    def test_with_videos_returns_true(self):
        vid = MagicMock()
        ri = RunInput(input_content="hello", videos=[vid])
        assert ri.contains_media()

    def test_with_audios_returns_true(self):
        aud = MagicMock()
        ri = RunInput(input_content="hello", audios=[aud])
        assert ri.contains_media()

    def test_with_files_returns_true(self):
        f = MagicMock()
        ri = RunInput(input_content="hello", files=[f])
        assert ri.contains_media()

    def test_empty_lists_returns_false(self):
        ri = RunInput(input_content="hello", images=[], videos=[], audios=[], files=[])
        assert not ri.contains_media()


# ---------------------------------------------------------------------------
# RunInput.input_content_string
# ---------------------------------------------------------------------------

class TestRunInputContentString:
    def test_str_input_returns_as_is(self):
        ri = RunInput(input_content="plain text")
        assert ri.input_content_string() == "plain text"

    def test_base_model_input_serialized(self):
        from pydantic import BaseModel as PydanticBase

        class MyModel(PydanticBase):
            x: int = 1
            y: str = "hello"

        ri = RunInput(input_content=MyModel())
        result = ri.input_content_string()
        assert "1" in result

    def test_other_type_falls_back_to_str(self):
        ri = RunInput(input_content=42)
        assert ri.input_content_string() == "42"

    def test_dict_falls_through_to_str(self):
        ri = RunInput(input_content={"key": "value"})
        result = ri.input_content_string()
        assert "key" in result


# ---------------------------------------------------------------------------
# RunInput.to_dict
# ---------------------------------------------------------------------------

class TestRunInputToDict:
    def test_str_input_content(self):
        ri = RunInput(input_content="hello")
        d = ri.to_dict()
        assert d["input_content"] == "hello"

    def test_no_media_no_keys(self):
        ri = RunInput(input_content="x")
        d = ri.to_dict()
        assert "images" not in d
        assert "videos" not in d

    def test_dict_input_content(self):
        ri = RunInput(input_content={"k": "v"})
        d = ri.to_dict()
        assert d["input_content"] == {"k": "v"}

    def test_empty_input_no_entry(self):
        ri = RunInput(input_content="")
        d = ri.to_dict()
        # empty str is still truthy for the dict key
        assert "input_content" in d

    def test_base_model_input_serialized_in_to_dict(self):
        from pydantic import BaseModel as PydanticBase

        class Payload(PydanticBase):
            value: int = 99

        ri = RunInput(input_content=Payload())
        d = ri.to_dict()
        assert d["input_content"]["value"] == 99


# ---------------------------------------------------------------------------
# RunOutput properties
# ---------------------------------------------------------------------------

_BASE = dict(
    run_id="run-1",
    session_id="sess-1",
    user_id="user-1",
    model="claude-3",
    agent_name="agent",
)


class TestRunOutputProperties:
    def test_is_paused_true(self):
        ro = RunOutput(**_BASE, status=RunStatus.PAUSED)
        assert ro.is_paused is True

    def test_is_paused_false(self):
        ro = RunOutput(**_BASE, status=RunStatus.RUNNING)
        assert ro.is_paused is False

    def test_is_cancelled_true(self):
        ro = RunOutput(**_BASE, status=RunStatus.CANCELLED)
        assert ro.is_cancelled is True

    def test_is_cancelled_false(self):
        ro = RunOutput(**_BASE, status=RunStatus.COMPLETED)
        assert ro.is_cancelled is False

    def test_is_sub_agent_response_false_when_no_delegation(self):
        ro = RunOutput(**_BASE)
        assert ro.is_sub_agent_response is False

    def test_is_sub_agent_response_true_via_delegated_from(self):
        ro = RunOutput(**_BASE, delegated_from="parent-agent")
        assert ro.is_sub_agent_response is True

    def test_is_sub_agent_response_true_via_parent_run_id(self):
        ro = RunOutput(**_BASE, parent_run_id="parent-run")
        assert ro.is_sub_agent_response is True

    def test_active_requirements_empty_when_no_requirements(self):
        ro = RunOutput(**_BASE)
        assert ro.active_requirements == []

    def test_active_requirements_filters_resolved(self):
        req_resolved = MagicMock()
        req_resolved.is_resolved.return_value = True
        req_unresolved = MagicMock()
        req_unresolved.is_resolved.return_value = False
        ro = RunOutput(**_BASE, requirements=[req_resolved, req_unresolved])
        active = ro.active_requirements
        assert len(active) == 1
        assert active[0] is req_unresolved

    def test_tools_requiring_confirmation_empty_when_no_tools(self):
        ro = RunOutput(**_BASE)
        assert ro.tools_requiring_confirmation == []

    def test_tools_requiring_confirmation_filtered(self):
        tool_yes = MagicMock()
        tool_yes.requires_confirmation = True
        tool_no = MagicMock()
        tool_no.requires_confirmation = False
        ro = RunOutput(**_BASE, tools=[tool_yes, tool_no])
        assert len(ro.tools_requiring_confirmation) == 1
        assert ro.tools_requiring_confirmation[0] is tool_yes

    def test_tools_requiring_user_input_empty_when_no_tools(self):
        ro = RunOutput(**_BASE)
        assert ro.tools_requiring_user_input == []

    def test_tools_requiring_user_input_filtered(self):
        tool_yes = MagicMock()
        tool_yes.requires_user_input = True
        tool_no = MagicMock()
        tool_no.requires_user_input = False
        ro = RunOutput(**_BASE, tools=[tool_yes, tool_no])
        result = ro.tools_requiring_user_input
        assert len(result) == 1
        assert result[0] is tool_yes

    def test_tools_awaiting_external_execution_empty_when_no_tools(self):
        ro = RunOutput(**_BASE)
        assert ro.tools_awaiting_external_execution == []

    def test_tools_awaiting_external_execution_filtered(self):
        tool_yes = MagicMock()
        tool_yes.external_execution_required = True
        tool_no = MagicMock()
        tool_no.external_execution_required = False
        ro = RunOutput(**_BASE, tools=[tool_yes, tool_no])
        result = ro.tools_awaiting_external_execution
        assert len(result) == 1
        assert result[0] is tool_yes


# ---------------------------------------------------------------------------
# RunInput.input_content_string – Message and list of Messages
# ---------------------------------------------------------------------------


class TestRunInputContentStringExtended:
    def test_message_input_returns_json(self):
        msg = Message(role="user", content="Hello")
        ri = RunInput(input_content=msg)
        result = ri.input_content_string()
        assert "Hello" in result

    def test_list_of_messages_returns_json(self):
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="World"),
        ]
        ri = RunInput(input_content=messages)
        result = ri.input_content_string()
        assert "Hello" in result
        assert "World" in result


# ---------------------------------------------------------------------------
# RunInput.to_dict – Message and list branches
# ---------------------------------------------------------------------------


class TestRunInputToDictExtended:
    def test_message_input_content(self):
        msg = Message(role="user", content="msg text")
        ri = RunInput(input_content=msg)
        d = ri.to_dict()
        assert "input_content" in d
        assert isinstance(d["input_content"], dict)

    def test_list_of_messages_input_content(self):
        messages = [Message(role="user", content="hello")]
        ri = RunInput(input_content=messages)
        d = ri.to_dict()
        assert isinstance(d["input_content"], list)

    def test_list_of_dicts_input_content(self):
        content_list = [{"text": "hello", "images": []}, {"text": "world"}]
        ri = RunInput(input_content=content_list)
        d = ri.to_dict()
        assert isinstance(d["input_content"], list)

    def test_images_serialized_in_to_dict(self):
        img = MagicMock()
        img.to_dict.return_value = {"type": "image", "data": "..."}
        ri = RunInput(input_content="hello", images=[img])
        d = ri.to_dict()
        assert "images" in d
        assert d["images"][0]["type"] == "image"

    def test_videos_serialized_in_to_dict(self):
        vid = MagicMock()
        vid.to_dict.return_value = {"type": "video", "url": "..."}
        ri = RunInput(input_content="hello", videos=[vid])
        d = ri.to_dict()
        assert "videos" in d

    def test_audios_serialized_in_to_dict(self):
        aud = MagicMock()
        aud.to_dict.return_value = {"type": "audio", "data": "..."}
        ri = RunInput(input_content="hello", audios=[aud])
        d = ri.to_dict()
        assert "audios" in d

    def test_files_serialized_in_to_dict(self):
        f = MagicMock()
        f.to_dict.return_value = {"type": "file", "name": "test.txt"}
        ri = RunInput(input_content="hello", files=[f])
        d = ri.to_dict()
        assert "files" in d


# ---------------------------------------------------------------------------
# RunInput.from_dict
# ---------------------------------------------------------------------------


class TestRunInputFromDict:
    def test_from_dict_with_string_input(self):
        d = {"input_content": "hello"}
        ri = RunInput.from_dict(d)
        assert ri.input_content == "hello"

    def test_from_dict_empty_dict(self):
        d = {}
        ri = RunInput.from_dict(d)
        assert ri.input_content == ""
        assert ri.images is None
        assert ri.videos is None

    def test_from_dict_with_no_media(self):
        d = {"input_content": "test"}
        ri = RunInput.from_dict(d)
        assert ri.files is None
        assert ri.audios is None


# ---------------------------------------------------------------------------
# RunCancelledEvent.is_cancelled property
# ---------------------------------------------------------------------------


class TestRunCancelledEvent:
    def test_is_cancelled_returns_true(self):
        e = RunCancelledEvent(run_id="r1", session_id="s1", model="m", agent_name="a")
        assert e.is_cancelled is True

    def test_reason_can_be_set(self):
        e = RunCancelledEvent(
            run_id="r1", session_id="s1", model="m", agent_name="a",
            reason="User requested cancellation",
        )
        assert e.reason == "User requested cancellation"


# ---------------------------------------------------------------------------
# SandboxInitializedEvent.to_dict with sandbox_info
# ---------------------------------------------------------------------------


class TestSandboxInitializedEvent:
    def test_to_dict_without_sandbox_info(self):
        e = SandboxInitializedEvent(run_id="r1", session_id="s1", model="m", agent_name="a")
        d = e.to_dict()
        assert "sandbox_info" not in d

    def test_to_dict_with_sandbox_info(self):
        from ii_agent.agents.sandboxes.schemas import SandboxInfo

        si = SandboxInfo(id="sb-1", provider="e2b", session_id="sess-1", status="running")
        e = SandboxInitializedEvent(
            run_id="r1", session_id="s1", model="m", agent_name="a",
            sandbox_info=si,
        )
        d = e.to_dict()
        assert "sandbox_info" in d
        assert d["sandbox_info"]["id"] == "sb-1"


# ---------------------------------------------------------------------------
# CustomEvent construction
# ---------------------------------------------------------------------------


class TestCustomEvent:
    def test_custom_event_stores_arbitrary_attributes(self):
        e = CustomEvent(my_key="my_value", count=42)
        assert e.my_key == "my_value"
        assert e.count == 42


# ---------------------------------------------------------------------------
# run_output_event_from_dict
# ---------------------------------------------------------------------------


class TestRunOutputEventFromDict:
    def test_creates_run_started_event(self):
        d = {
            "event": "RunStarted",
            "run_id": "r1",
            "session_id": "s1",
            "user_id": "u1",
            "model": "m",
            "agent_name": "a",
        }
        event = run_output_event_from_dict(d)
        assert isinstance(event, RunStartedEvent)

    def test_raises_for_unknown_event_type(self):
        d = {"event": "UnknownEventXYZ"}
        with pytest.raises(ValueError, match="Unknown event type"):
            run_output_event_from_dict(d)


# ---------------------------------------------------------------------------
# RunOutput.add_member_run – media aggregation
# ---------------------------------------------------------------------------


_CHILD_BASE = dict(
    run_id="child-run",
    session_id="sess-1",
    user_id="user-1",
    model="claude-3",
    agent_name="child-agent",
)


class TestRunOutputAddMemberRun:
    def test_add_member_run_appends_to_member_responses(self):
        parent = RunOutput(**_BASE)
        child = RunOutput(**_CHILD_BASE)
        parent.add_member_run(child)
        assert parent.member_responses is not None
        assert child in parent.member_responses

    def test_add_member_run_aggregates_images(self):
        parent = RunOutput(**_BASE)
        img = MagicMock()
        child = RunOutput(**_CHILD_BASE, images=[img])
        parent.add_member_run(child)
        assert parent.images is not None
        assert img in parent.images

    def test_add_member_run_aggregates_videos(self):
        parent = RunOutput(**_BASE)
        vid = MagicMock()
        child = RunOutput(**_CHILD_BASE, videos=[vid])
        parent.add_member_run(child)
        assert parent.videos is not None
        assert vid in parent.videos

    def test_add_member_run_aggregates_audio(self):
        parent = RunOutput(**_BASE)
        aud = MagicMock()
        child = RunOutput(**_CHILD_BASE, audio=[aud])
        parent.add_member_run(child)
        assert parent.audio is not None
        assert aud in parent.audio

    def test_add_member_run_aggregates_files(self):
        parent = RunOutput(**_BASE)
        f = MagicMock()
        child = RunOutput(**_CHILD_BASE, files=[f])
        parent.add_member_run(child)
        assert parent.files is not None
        assert f in parent.files

    def test_add_multiple_member_runs(self):
        parent = RunOutput(**_BASE)
        child1 = RunOutput(**_CHILD_BASE)
        child2 = RunOutput(run_id="child-2", session_id="sess-1", user_id="user-1", model="m", agent_name="a")
        parent.add_member_run(child1)
        parent.add_member_run(child2)
        assert len(parent.member_responses) == 2


# ---------------------------------------------------------------------------
# RunOutput.to_dict – various optional fields
# ---------------------------------------------------------------------------


class TestRunOutputToDict:
    def test_basic_to_dict_includes_required_fields(self):
        ro = RunOutput(**_BASE, content="Hello")
        d = ro.to_dict()
        assert d["run_id"] == "run-1"
        assert d["session_id"] == "sess-1"
        assert d["content"] == "Hello"

    def test_to_dict_with_messages(self):
        ro = RunOutput(**_BASE, messages=[Message(role="user", content="hello")])
        d = ro.to_dict()
        assert "messages" in d
        assert isinstance(d["messages"], list)
        assert len(d["messages"]) == 1

    def test_to_dict_with_metadata(self):
        ro = RunOutput(**_BASE, metadata={"key": "value"})
        d = ro.to_dict()
        assert "metadata" in d
        assert d["metadata"]["key"] == "value"

    def test_to_dict_with_images(self):
        from ii_agent.files.media import Image

        img = Image(url="http://example.com/img.jpg")
        ro = RunOutput(**_BASE, images=[img])
        d = ro.to_dict()
        assert "images" in d
        assert len(d["images"]) == 1
        assert d["images"][0]["url"] == "http://example.com/img.jpg"

    def test_to_dict_status_serialized(self):
        ro = RunOutput(**_BASE, status=RunStatus.COMPLETED)
        d = ro.to_dict()
        assert d["status"] == RunStatus.COMPLETED.value

    def test_to_dict_with_member_responses(self):
        child = RunOutput(**_CHILD_BASE)
        parent = RunOutput(**_BASE, member_responses=[child])
        d = parent.to_dict()
        assert "member_responses" in d
        assert isinstance(d["member_responses"], list)

    def test_to_dict_with_no_optional_fields(self):
        ro = RunOutput(**_BASE)
        d = ro.to_dict()
        assert "run_id" in d
        assert "messages" not in d
        assert "metadata" not in d
        assert "images" not in d


# ---------------------------------------------------------------------------
# RunOutput.from_dict
# ---------------------------------------------------------------------------


class TestRunOutputFromDict:
    def _minimal_dict(self):
        return {
            "run_id": "run-1",
            "session_id": "sess-1",
            "user_id": "user-1",
            "model": "claude-3",
            "agent_name": "agent",
        }

    def test_from_dict_basic(self):
        d = self._minimal_dict()
        ro = RunOutput.from_dict(d)
        assert ro.run_id == "run-1"
        assert ro.session_id == "sess-1"
        assert ro.model == "claude-3"

    def test_from_dict_with_messages(self):
        d = self._minimal_dict()
        d["messages"] = [{"role": "user", "content": "hello"}]
        ro = RunOutput.from_dict(d)
        assert ro.messages is not None
        assert len(ro.messages) == 1
        assert ro.messages[0].role == "user"

    def test_from_dict_status_string_converted_to_enum(self):
        d = self._minimal_dict()
        d["status"] = "completed"
        ro = RunOutput.from_dict(d)
        assert ro.status == RunStatus.COMPLETED

    def test_from_dict_invalid_status_defaults_to_completed(self):
        d = self._minimal_dict()
        d["status"] = "unknown_status_xyz"
        ro = RunOutput.from_dict(d)
        assert ro.status == RunStatus.COMPLETED

    def test_from_dict_with_member_responses(self):
        d = self._minimal_dict()
        child = dict(self._minimal_dict())
        child["run_id"] = "child-1"
        d["member_responses"] = [child]
        ro = RunOutput.from_dict(d)
        assert ro.member_responses is not None
        assert len(ro.member_responses) == 1
        assert ro.member_responses[0].run_id == "child-1"

    def test_from_dict_with_input_data(self):
        d = self._minimal_dict()
        d["input"] = {"input_content": "test question"}
        ro = RunOutput.from_dict(d)
        assert ro.input is not None
        assert ro.input.input_content == "test question"

    def test_from_dict_pops_events_key(self):
        """Events key is ignored during from_dict."""
        d = self._minimal_dict()
        d["events"] = [{"event": "RunStarted"}]
        ro = RunOutput.from_dict(d)
        assert ro.run_id == "run-1"
