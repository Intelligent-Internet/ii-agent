from __future__ import annotations

import pytest

from ii_agent_tools.integrations.video_generation.config import VideoGenerateConfig
from ii_agent_tools.integrations.video_generation.factory import (
    create_video_generation_client,
)
from ii_agent_tools.integrations.video_generation.minimax import (
    DEFAULT_MODEL,
    MiniMaxVideoGenerationClient,
)


def _client() -> MiniMaxVideoGenerationClient:
    # output_bucket left unset so no GCS client is constructed.
    return MiniMaxVideoGenerationClient(api_key="test-key")


def test_resolve_model_name_defaults_and_passthrough():
    client = _client()
    assert client._resolve_model_name(None) == DEFAULT_MODEL
    assert client._resolve_model_name("") == DEFAULT_MODEL
    assert client._resolve_model_name("T2V-01") == "T2V-01"


def test_resolve_model_name_uses_configured_default():
    client = MiniMaxVideoGenerationClient(api_key="test-key", model_name="MiniMax-Hailuo-2.3-Fast")
    assert client._resolve_model_name(None) == "MiniMax-Hailuo-2.3-Fast"


def test_build_payload_text_to_video():
    client = _client()
    payload = client._build_payload(
        model="MiniMax-Hailuo-2.3",
        prompt="a cat surfing",
        first_frame_image=None,
        duration_seconds=6,
        resolution="720p",
        provider_payload=None,
    )
    assert payload["model"] == "MiniMax-Hailuo-2.3"
    assert payload["prompt"] == "a cat surfing"
    assert payload["duration"] == 6
    # Lowercase Veo-style resolution is not a MiniMax token, so it is dropped.
    assert "resolution" not in payload
    assert "first_frame_image" not in payload


def test_build_payload_forwards_native_resolution_token():
    client = _client()
    payload = client._build_payload(
        model="MiniMax-Hailuo-2.3",
        prompt="a cat surfing",
        first_frame_image=None,
        duration_seconds=0,
        resolution="1080P",
        provider_payload=None,
    )
    assert payload["resolution"] == "1080P"
    assert "duration" not in payload


def test_build_payload_image_to_video():
    client = _client()
    payload = client._build_payload(
        model="I2V-01",
        prompt="pan slowly",
        first_frame_image="https://img.example/first.png",
        duration_seconds=6,
        resolution="720p",
        provider_payload=None,
    )
    assert payload["first_frame_image"] == "https://img.example/first.png"
    assert payload["prompt"] == "pan slowly"
    assert payload["model"] == "I2V-01"


def test_build_payload_provider_payload_is_allowlisted():
    client = _client()
    payload = client._build_payload(
        model="MiniMax-Hailuo-2.3",
        prompt="a cat surfing",
        first_frame_image=None,
        duration_seconds=6,
        resolution="720p",
        provider_payload={
            "prompt_optimizer": True,
            "fast_pretreatment": True,
            "callback_url": "https://cb.example/hook",
            "not_a_field": "dropped",
        },
    )
    assert payload["prompt_optimizer"] is True
    assert payload["fast_pretreatment"] is True
    assert payload["callback_url"] == "https://cb.example/hook"
    assert "not_a_field" not in payload


def test_check_base_resp_raises_on_error_code():
    client = _client()
    # Zero / missing status codes are accepted.
    client._check_base_resp({"base_resp": {"status_code": 0}})
    client._check_base_resp({"task_id": "123"})
    with pytest.raises(RuntimeError, match="MiniMax API error 1004"):
        client._check_base_resp(
            {"base_resp": {"status_code": 1004, "status_msg": "invalid api key"}}
        )


def test_params_include_group_id_when_configured():
    client = MiniMaxVideoGenerationClient(api_key="test-key", group_id="grp-1")
    params = client._params({"task_id": "abc"})
    assert params == {"task_id": "abc", "GroupId": "grp-1"}

    no_group = MiniMaxVideoGenerationClient(api_key="test-key")
    no_group.group_id = None
    assert no_group._params({"task_id": "abc"}) == {"task_id": "abc"}


def test_factory_registers_minimax_provider():
    config = VideoGenerateConfig(minimax_api_key="test-key")
    client = create_video_generation_client(config, provider="minimax")
    assert isinstance(client, MiniMaxVideoGenerationClient)
    assert client.base_url == "https://api.minimax.io/v1"


def test_factory_minimax_alias_and_missing_key():
    config = VideoGenerateConfig(minimax_api_key="test-key")
    client = create_video_generation_client(config, provider="minimaxi")
    assert isinstance(client, MiniMaxVideoGenerationClient)

    with pytest.raises(ValueError, match="minimax provider requires minimax_api_key"):
        create_video_generation_client(VideoGenerateConfig(), provider="minimax")
