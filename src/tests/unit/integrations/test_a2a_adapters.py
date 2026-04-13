from types import SimpleNamespace


from ii_agent.integrations.a2a.context_adapter import extract_request_payload


def test_extract_request_payload_merges_metadata_sources():
    context = SimpleNamespace(
        metadata={
            "ii-agent": {
                "tool_args": {"web_search": True},
                "sandbox": {"reuse": "true", "timeout": "120"},
                "user": {"user_id": "u1", "api_key": "k1"},
            }
        },
        configuration=None,
        message=SimpleNamespace(
            metadata={"ii-agent": {"tool_args": {"image_search": True}}},
            parts=[],
            content=None,
        ),
    )

    payload = extract_request_payload(context)

    assert payload.tool_args["web_search"] is True
    assert payload.tool_args["image_search"] is True
    assert payload.sandbox.reuse is True
    assert payload.sandbox.timeout_seconds == 120
    assert payload.user.user_id == "u1"
    assert payload.user.api_key == "k1"


def test_extract_request_payload_handles_missing_section_gracefully():
    context = SimpleNamespace(metadata={}, configuration=None, message=None)

    payload = extract_request_payload(context)

    assert payload.tool_args == {}
    assert payload.sandbox.reuse is False
    assert payload.user.user_id is None
