# Briefing Note: Vision Support via A2A → GitHub Copilot CLI/SDK

**Audience:** Engineering agents who believe vision/image input is unsupported through the A2A → Copilot inner loop.
**Status:** Implemented and shipping in `ii-agent` since the chat-A2A inner loop landed. This note explains *what* the SDK supports, *how* `ii-agent` wires it, and *where* to look in code.
**TL;DR:** It is fully supported. Copilot SDK accepts image attachments via `session.send(attachments=[…])`. A2A carries them as `FilePart` (`FileWithBytes` or `FileWithUri`). `ii-agent` translates between the two in `multimodal.py` (inbound) and `copilot_backend._parts_to_attachments()` (SDK side).

---

## 1. The claim is wrong — here is the proof from the SDK

The official GitHub Copilot SDK exposes image attachments as a first-class parameter on `Session.send()`. Two attachment shapes are supported:

```python
# File on disk
await session.send(
    "What's in this image?",
    attachments=[{"type": "file", "path": "/path/to/image.jpg"}],
)

# Inline base64 blob
await session.send(
    "What's in this image?",
    attachments=[{"type": "blob", "data": base64_data, "mimeType": "image/png"}],
)
```

Supported MIME types: `image/png`, `image/jpeg`, `image/gif`, `image/webp` (and other common image types accepted by the underlying Copilot model).

**Online references (authoritative):**

- GitHub Copilot CLI / SDK announcement and docs index: <https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli>
- GitHub Copilot SDK release notes (image attachments documented): <https://github.blog/changelog/?label=copilot>
- Copilot CLI `--image` flag (the SDK is the programmatic equivalent): <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli>
- Open issue tracking *non-image* attachment expansion (proves images are the supported case today): <https://github.com/github/copilot-cli/issues> (search `attachments`)

Internal reference inside this repo:

- [docs/design-docs/copilot-sdk-integration-assessment.md](copilot-sdk-integration-assessment.md) §Q6 “Vision / Image Support — **FULLY SUPPORTED**” and §2 feature-mapping table row `Vision/images`.

If your agent reported “not possible,” it was likely looking at the Codex backend (text-only) or at the legacy `gh copilot suggest` CLI (no streaming, no attachments). Neither is the right surface: the Copilot **SDK** (`from copilot import CopilotClient`) is what the A2A adapter uses.

---

## 2. The A2A protocol already carries images

A2A (`a2a-sdk`) defines `Part` as a discriminated union: `TextPart | FilePart | DataPart`. `FilePart` itself wraps either:

- `FileWithBytes(name, bytes, mime_type)` — base64-encoded inline payload
- `FileWithUri(name, uri, mime_type)` — pointer to a fetchable resource (`file://`, `https://`, etc.)

Spec: <https://a2a-protocol.org/latest/specification/> (see “Message Parts” and “File Parts”).
SDK reference: <https://github.com/google/a2a-sdk-python> → `a2a.types.FilePart`, `FileWithBytes`, `FileWithUri`.

So the wire format is not the blocker. The only work is translating both sides.

---

## 3. How `ii-agent` wires it end-to-end

```
Chat user uploads image
        │
        ▼
ChatService → A2AChatTurnLoop._build_a2a_messages()
   (BinaryContent → A2AImage(content=bytes, mime_type=…))
   (ImageURLContent → A2AImage(url=…))
        │  POST /a2a/stream  (HTTPS, JSON body)
        ▼
adapter_server._event_source()
   ├─ extract_user_content(messages)              ← latest user turn
   └─ extract_historical_image_parts(messages)    ← prior turns (so follow-ups still see image)
        │  (returns list[Part] containing FilePart objects)
        ▼
CopilotBackend.stream(prompt, parts=…)
        │
        ▼
_parts_to_attachments(parts)
   ├─ FileWithUri + file://   → {"type": "file", "path": uri[7:]}
   ├─ FileWithUri + https://  → download to tmpfile → {"type": "file", "path": tmp}
   └─ FileWithBytes           → base64.b64decode → tmpfile → {"type": "file", "path": tmp}
        │
        ▼
session.send({"prompt": …, "attachments": attachments})
        │
        ▼
   GitHub Copilot LLM (vision-enabled)
```

### Files to read (in order)

1. **Inbound translation (chat → A2A):**
   [src/ii_agent/chat/application/a2a_turn_loop_service.py](../../src/ii_agent/chat/application/a2a_turn_loop_service.py#L420-L490) → `_build_a2a_messages()` converts `BinaryContent` / `ImageURLContent` parts into `Image` objects attached to the dict under the `images` key.

2. **A2A `Part` extraction:**
   [src/ii_agent/integrations/a2a/multimodal.py](../../src/ii_agent/integrations/a2a/multimodal.py) → `extract_user_content()` (current turn) and `extract_historical_image_parts()` (prior turns). These return `list[Part]` with `FilePart` for every image. `_image_dict_to_part()` is the one-image conversion helper — it picks `FileWithUri` vs `FileWithBytes` based on which keys are present.

3. **Adapter dispatch:**
   [src/ii_agent/integrations/a2a/adapter_server.py](../../src/ii_agent/integrations/a2a/adapter_server.py#L588-L640) → `_event_source()` calls the extractors, then forwards `parts=…` to `backend.stream(...)` whenever `has_multimodal_parts(parts)` is true.

4. **Copilot SDK adapter (the actual “image → SDK” step):**
   [src/ii_agent/integrations/a2a/copilot_backend.py](../../src/ii_agent/integrations/a2a/copilot_backend.py#L109-L210) → `_parts_to_attachments()` builds the SDK attachment dicts and tracks tempfiles for cleanup. [Lines 620-640](../../src/ii_agent/integrations/a2a/copilot_backend.py#L620-L640) show it being called from `stream()`. [Lines 910-918](../../src/ii_agent/integrations/a2a/copilot_backend.py#L910-L918) show `attachments` being attached to `send_opts` for `session.send()`. [Lines 651-655](../../src/ii_agent/integrations/a2a/copilot_backend.py#L651-L655) handle tempfile cleanup in a `finally` block.

5. **Test coverage:**
   `src/tests/unit/integrations/test_a2a_multimodal.py` (38 cases incl. base64 round-trip, URI passthrough, MIME inference) and `test_a2a_multimodal_backends.py` (per-backend attachment construction, including the Copilot path).

---

## 4. Implementation rules a re-implementer must follow

### 4.1 Use the SDK, not the legacy CLI

```python
from copilot import CopilotClient   # the official SDK package
client = CopilotClient({"auto_start": True, "use_logged_in_user": True, "cwd": "/workspace"})
await client.start()
session = await client.create_session({"streaming": True, "working_directory": "/workspace"})
```

The legacy `gh copilot suggest` shell command is **not** the integration point. Vision lives on `Session.send(..., attachments=[...])`.

### 4.2 SDK accepts only `file` and `blob` attachments — there is no inline-image-by-bytes-on-disk-free path

The SDK reads attachments from a local path. For `FileWithBytes` you **must** materialize a tempfile, hand the path to the SDK, and clean up after the turn. The reference pattern:

```python
fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="copilot_attach_")
os.write(fd, base64.b64decode(file_obj.bytes))
os.close(fd)
attachments.append({"type": "file", "path": tmp_path})
temp_files.append(tmp_path)            # remember to delete in finally:
```

Yes, the SDK *also* documents `{"type": "blob", "data": …, "mimeType": …}`. Both work. `ii-agent` chose `file` for both paths because it is uniform and avoids a 2nd base64 round-trip on long-lived sessions. Pick one and document it.

### 4.3 Filter MIME types

Only forward image MIMEs. Other `FilePart`s should be skipped (or routed elsewhere). See `_IMAGE_MIME_PREFIXES` in `copilot_backend.py`. Non-image parts are logged and dropped — do not let arbitrary binary content reach the SDK; it will reject or, worse, silently fail.

### 4.4 Handle remote URIs

If the `FileWithUri.uri` is `https://…`, download with `httpx`, write to tempfile, attach the local path. Do **not** pass the URL straight to the SDK; the SDK does not fetch.

### 4.5 Forward historical images

For multi-turn vision conversations, prior-turn images must be re-attached because Copilot SDK sessions in this integration are recreated per-run (clean slate every turn — see the comment on `_get_or_create_session`). `extract_historical_image_parts()` does this. Without it, “what about the second image?” fails.

### 4.6 Clean up tempfiles

Use a `try/finally` around the streaming loop and call `_cleanup_temp_files(temp_files)`. Tempfile leakage in `/tmp` will eventually OOM the sandbox.

### 4.7 Watch the size budget

Copilot has per-request size limits (in practice ~5 MB per image — see image-handling fix in repo memory `image-handling-5mb-issue.md`). Resize/compress before attachment if user uploads exceed it, or surface a clear error.

---

## 5. Common failure modes (and what they actually mean)

| Symptom | Real cause |
|---|---|
| “SDK rejects attachments” | You probably called `session.send("text")` (positional) — `attachments=` must be a kwarg in a dict body or a second arg per SDK version. Check your installed `github-copilot-sdk` signature. |
| “Image arrived but model ignored it” | You sent a `DataPart` instead of a `FilePart`, or skipped the image because MIME prefix check failed. Inspect the adapter logs — `_parts_to_attachments` logs every skip. |
| “Works for first image, fails for follow-ups” | Forgot `extract_historical_image_parts()`. Sessions are recreated per turn. |
| “Tempfiles pile up” | Missing `_cleanup_temp_files()` in `finally:`. |
| “Codex backend can’t see images” | Correct — Codex backend in this repo is text-only. Use the **Copilot** backend (`AGENT_A2A_BACKEND=copilot`) for vision. |
| “Adapter on a different host can’t open my `file://` URI” | Use `FileWithBytes` instead, or pre-stage the file inside the sandbox. The adapter and Copilot CLI both read from their own filesystem. |

---

## 6. Configuration to enable vision in chat A2A

```bash
AGENT_CHAT_INNER_LOOP_MODE=a2a
AGENT_A2A_BACKEND=copilot                 # NOT codex (text-only)
AGENT_A2A_AGENT_URL=http://a2a-adapter:18100
AGENT_A2A_CHAT_STRICT=true                # crash early on misconfig
```

The adapter sidecar (`a2a-adapter` service in `docker/docker-compose.local.yaml`) is sandbox-independent — see [docs/design-docs/chat-a2a-adapter-sidecar.md](chat-a2a-adapter-sidecar.md). Vision works in both the sidecar deployment and the per-sandbox deployment.

---

## 7. Verification recipe

1. Start the local stack: `./scripts/stack_control.sh start`.
2. Open a chat session and attach a PNG/JPEG.
3. Ask “what is in this image?”
4. Tail adapter logs:
   ```bash
   ./scripts/stack_control.sh logs a2a-adapter -f | grep -E 'multimodal|attachment|image'
   ```
   Expect to see `extract_user_content: ... media=1` and `CopilotBackend: forwarding 1 image attachment(s) to Copilot SDK`.
5. Confirm the model response references image content.

If steps 4 and 5 both succeed, vision is working end-to-end.

---

## 8. Bottom line for the other agent

Re-read [copilot-sdk-integration-assessment.md §Q6](copilot-sdk-integration-assessment.md), then read these three files in order:

1. `src/ii_agent/chat/application/a2a_turn_loop_service.py::_build_a2a_messages`
2. `src/ii_agent/integrations/a2a/multimodal.py::_image_dict_to_part`
3. `src/ii_agent/integrations/a2a/copilot_backend.py::_parts_to_attachments`

The pipeline already exists, ships, and is tested. Don’t reinvent it — extend it (e.g. add audio, larger files) following the same pattern.
