from __future__ import annotations

import httpx
import pytest

from ii_agent_tools.integrations.video_generation.config import VideoGenerateConfig
from ii_agent_tools.integrations.video_generation.factory import (
    create_video_generation_client,
)
from ii_agent_tools.integrations.video_generation.minimax import (
    DEFAULT_MODEL,
    MiniMaxVideoGenerationClient,
)
from ii_agent_tools.integrations.video_generation.service import (
    get_model_direct_supported_duration_seconds,
    is_supported_video_model,
)


def _client() -> MiniMaxVideoGenerationClient:
    # output_bucket left unset so no GCS client is constructed.
    return MiniMaxVideoGenerationClient(api_key="test-key")


def test_resolve_model_name_defaults_and_passthrough():
    client = _client()
    assert client._resolve_model_name(None) == DEFAULT_MODEL
    assert client._resolve_model_name("") == DEFAULT_MODEL
    assert client._resolve_model_name("T2V-01") == "T2V-01"

    with pytest.raises(ValueError, match="Unsupported MiniMax video model"):
        client._resolve_model_name("unknown-model")


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


def test_build_v2_payload_text_to_video():
    client = _client()
    payload = client._build_v2_payload(
        model="MiniMax-H3",
        prompt="A city waking at sunrise",
        first_frame_image=None,
        last_frame_image=None,
        reference_images=None,
        duration_seconds=5,
        aspect_ratio="16:9",
        provider_payload={"callback_url": "https://cb.example/hook"},
    )

    assert payload == {
        "model": "MiniMax-H3",
        "content": [{"type": "text", "text": "A city waking at sunrise"}],
        "resolution": "2K",
        "duration": 5,
        "ratio": "16:9",
        "callback_url": "https://cb.example/hook",
    }


def test_build_v2_payload_frames_and_cn_watermark():
    client = MiniMaxVideoGenerationClient(
        api_key="test-key",
        base_url="https://api.minimaxi.com/v1",
    )
    payload = client._build_v2_payload(
        model="MiniMax-H3",
        prompt="Move through the scene",
        first_frame_image="https://img.example/first.png",
        last_frame_image="https://img.example/last.png",
        reference_images=None,
        duration_seconds=8,
        aspect_ratio="9:16",
        provider_payload={"aigc_watermark": True},
    )

    assert payload["ratio"] == "adaptive"
    assert payload["aigc_watermark"] is True
    assert payload["content"][1]["role"] == "first_frame"
    assert payload["content"][2]["role"] == "last_frame"

    global_payload = _client()._build_v2_payload(
        model="MiniMax-H3",
        prompt="Move through the scene",
        first_frame_image=None,
        last_frame_image=None,
        reference_images=None,
        duration_seconds=8,
        aspect_ratio="9:16",
        provider_payload={"aigc_watermark": True},
    )
    assert "aigc_watermark" not in global_payload


def test_build_v2_payload_treats_unroled_image_as_first_frame():
    payload = _client()._build_v2_payload(
        model="MiniMax-H3",
        prompt="ignored when content is provided",
        first_frame_image=None,
        last_frame_image=None,
        reference_images=None,
        duration_seconds=5,
        aspect_ratio="16:9",
        provider_payload={
            "content": [
                {"type": "text", "text": "Animate this image"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://img.example/first.png"},
                },
            ]
        },
    )
    assert payload["ratio"] == "adaptive"


def test_build_v2_payload_validates_reference_content():
    client = _client()
    with pytest.raises(ValueError, match="requires a reference image or video"):
        client._build_v2_payload(
            model="MiniMax-H3",
            prompt="ignored when content is provided",
            first_frame_image=None,
            last_frame_image=None,
            reference_images=None,
            duration_seconds=5,
            aspect_ratio="16:9",
            provider_payload={
                "content": [
                    {"type": "text", "text": "Use the reference voice"},
                    {
                        "type": "audio_url",
                        "audio_url": {"url": "https://media.example/voice.mp3"},
                        "role": "reference_audio",
                    },
                ]
            },
        )


@pytest.mark.asyncio
async def test_v2_submit_and_poll_use_model_specific_endpoints():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "task-1"})
        return httpx.Response(
            200,
            json={
                "task": {
                    "id": "task-1",
                    "status": "succeeded",
                    "content": {"url": "https://media.example/video.mp4"},
                }
            },
        )

    client = _client()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        task_id = await client._submit(
            http_client,
            {"model": "MiniMax-H3"},
            api_version="v2",
        )
        download_url = await client._poll_v2_until_ready(http_client, task_id)

    assert download_url == "https://media.example/video.mp4"
    assert [request.url.path for request in requests] == [
        "/v2/video_generation",
        "/v2/query/video_generation/task-1",
    ]


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
    assert client.model_name == "MiniMax-H3"


def test_factory_minimax_alias_and_missing_key():
    config = VideoGenerateConfig(minimax_api_key="test-key")
    client = create_video_generation_client(config, provider="minimaxi")
    assert isinstance(client, MiniMaxVideoGenerationClient)

    with pytest.raises(ValueError, match="minimax provider requires minimax_api_key"):
        create_video_generation_client(VideoGenerateConfig(), provider="minimax")


def test_service_accepts_minimax_models_and_durations():
    assert is_supported_video_model("MiniMax-H3")
    assert is_supported_video_model("MiniMax-Hailuo-2.3-Fast")
    assert get_model_direct_supported_duration_seconds("MiniMax-H3") == list(range(4, 16))
    assert get_model_direct_supported_duration_seconds("I2V-01") == [6]
