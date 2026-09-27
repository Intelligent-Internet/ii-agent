"""Tests for ii_agent.agents.utils — common.check_type_compatibility + message.get_text_from_message."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from ii_agent.agents.models.message import Message
from ii_agent.agents.utils.agent import collect_joint_images, expire_historical_images
from ii_agent.files.media import Image


def test_expire_historical_images_only_changes_model_history():
    history = [
        Message(role="user", content="first", images=[Image(url="https://example.com/1.png")]),
        Message(role="assistant", content="reply"),
        Message(role="user", content="second", images=[Image(url="https://example.com/2.png")]),
        Message(role="user", content="third", images=[Image(url="https://example.com/3.png")]),
    ]
    model_history = deepcopy(history)
    expire_historical_images(model_history, retention_turns=2)
    assert [bool(message.images) for message in model_history if message.role == "user"] == [
        False,
        True,
        True,
    ]
    assert history[0].images

    expire_historical_images(model_history, retention_turns=0)
    assert all(not message.images for message in model_history)


def test_joint_images_only_include_recent_runs_and_current_upload():
    images = [Image(url=f"https://example.com/{index}.png") for index in range(4)]
    session = SimpleNamespace(
        runs=[
            SimpleNamespace(images=None, input=SimpleNamespace(images=[image]), run_id=str(index))
            for index, image in enumerate(images[:3])
        ]
    )
    current = SimpleNamespace(images=[images[3]])

    with patch("ii_agent.core.config.settings.get_settings") as settings:
        settings.return_value.agent.image_retention_turns = 2
        assert collect_joint_images(current, session) == [images[3], images[1], images[2]]
        settings.return_value.agent.image_retention_turns = 0
        assert collect_joint_images(current, session) == [images[3]]


def test_project_images_expire_after_five_follow_up_turns():
    history = [
        Message(role="user", images=[Image(url="https://example.com/old.png")]),
        *[Message(role="user", content=f"follow-up {turn}") for turn in range(4)],
    ]
    retained = deepcopy(history)
    expire_historical_images(retained, retention_turns=5)
    assert retained[0].images

    expired = deepcopy(history + [Message(role="user", content="fifth completed follow-up")])
    expire_historical_images(expired, retention_turns=5)
    assert not expired[0].images
    assert history[0].images


class TestCheckTypeCompatibilityExtra:
    def test_list_type_with_non_list_value(self):
        """Line 78, branch [77, 78]: origin is list but value is not a list."""
        from typing import List
        from ii_agent.agents.utils.common import check_type_compatibility

        result = check_type_compatibility("not_a_list", List[int])
        assert result is False

    def test_bare_list_type_with_non_list(self):
        from ii_agent.agents.utils.common import check_type_compatibility

        result = check_type_compatibility("not_a_list", list)
        assert result is False

    def test_custom_class_type_isinstance_check(self):
        """Lines 90-91, branch [87, 90]: expected_type is a custom class."""
        from ii_agent.agents.utils.common import check_type_compatibility

        class MyClass:
            pass

        instance = MyClass()
        result = check_type_compatibility(instance, MyClass)
        assert result is True

    def test_custom_class_type_not_instance(self):
        """Lines 90-91: isinstance returns False for wrong type."""
        from ii_agent.agents.utils.common import check_type_compatibility

        class MyClass:
            pass

        result = check_type_compatibility(42, MyClass)
        assert result is False

    def test_type_error_returns_true(self):
        """Lines 92-93, branch for TypeError: isinstance raises → return True."""
        from ii_agent.agents.utils.common import check_type_compatibility

        # Passing a non-type as expected_type causes TypeError in isinstance
        result = check_type_compatibility(42, 42)  # type: ignore
        assert result is True


class TestGetTextFromMessageEdgeCases:
    def test_get_text_with_none_returns_empty(self):
        """Lines 116, 118 + branches [111,116] [116,118]: None falls through to empty."""
        from ii_agent.agents.utils.message import get_text_from_message

        result = get_text_from_message(None)  # type: ignore
        assert result == ""

    def test_get_text_with_integer_returns_empty(self):
        """Non-standard type falls through all checks → empty."""
        from ii_agent.agents.utils.message import get_text_from_message

        result = get_text_from_message(42)  # type: ignore
        assert result == ""
