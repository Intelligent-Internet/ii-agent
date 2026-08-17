from types import SimpleNamespace


from ii_agent.integrations.a2a.extension_utils import (
    append_extension_issue,
    collect_requested_extensions,
)


def test_collect_requested_extensions_reads_context_and_message():
    context = SimpleNamespace(
        call_context=SimpleNamespace(requested_extensions={"ext.a", "ext.b"}),
        message=SimpleNamespace(extensions=["ext.c", 123]),
    )

    extensions = collect_requested_extensions(context)

    assert extensions == {"ext.a", "ext.b", "ext.c", "123"}


def test_append_extension_issue_initializes_issue_list():
    extension_info = {}

    append_extension_issue(
        extension_info,
        uri="urn:test",
        code="unsupported",
        detail="not supported",
    )

    assert extension_info["issues"][0]["uri"] == "urn:test"
    assert extension_info["issues"][0]["code"] == "unsupported"
