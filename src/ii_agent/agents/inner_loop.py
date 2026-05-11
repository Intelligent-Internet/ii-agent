from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Tuple, Type, Union

from pydantic import BaseModel

from ii_agent.agents.exceptions import AgentRunException, ModelProviderError
from ii_agent.agents.models.base import Model
from ii_agent.agents.models.message import Message
from ii_agent.agents.models.metrics import Metrics
from ii_agent.agents.models.response import ModelResponse, ModelResponseEvent, ToolExecution
from ii_agent.agents.runs import RunOutput
from ii_agent.agents.runs.agent import RunOutputEvent
from ii_agent.agents.tools.function import Function, FunctionCall, FunctionExecutionResult
from ii_agent.integrations.a2a.as_client import A2AStreamEvent, IIAgentA2AClient
from ii_agent.integrations.a2a.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    is_non_retriable,
)
from ii_agent.agents.tools.routing import ToolRoutingLayer
from ii_agent.core.logger import logger
from ii_agent.core.redis.cancel import RunCancelledException, raise_if_cancelled
from ii_agent.realtime.events.app_events import (
    CompactionAuthorityEvent,
    DelegationFallbackEvent,
    EventGroup,
)

# ---------------------------------------------------------------------------
# Alias mapping for CLI-native tool names → ii-agent Function names.
# The Copilot CLI has built-in tools that serve the same purpose as
# ii-agent bridged tools but under different names.  When the CLI LLM
# invokes a native name via bridge, this mapping resolves it to the
# registered Function so that server-side hooks (e.g. file upload in
# ``on_tool_end``) still execute.
# ---------------------------------------------------------------------------
_TOOL_NAME_ALIASES: Dict[str, str] = {
    "message_user": "send_user_files",
    "send_message": "send_user_files",
}


class InnerLoopStrategy(Protocol):
    """Protocol for pluggable inner-loop execution backends."""

    def aresponse_stream(
        self,
        *,
        model: Model,
        messages: List[Message],
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Union[Function, dict]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        tool_call_limit: Optional[int] = None,
        run_response: Optional[RunOutput] = None,
    ) -> AsyncIterator[Union[ModelResponse, RunOutputEvent]]: ...


@dataclass
class NativeInnerLoop:
    """Default strategy that delegates directly to the model provider."""

    async def aresponse_stream(
        self,
        *,
        model: Model,
        messages: List[Message],
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Union[Function, dict]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        tool_call_limit: Optional[int] = None,
        run_response: Optional[RunOutput] = None,
    ) -> AsyncIterator[Union[ModelResponse, RunOutputEvent]]:
        async for event in model.aresponse_stream(
            messages=messages,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            tool_call_limit=tool_call_limit,
            stream_model_response=True,
            run_response=run_response,
        ):
            yield event


@dataclass
class A2AInnerLoop:
    """A2A-backed strategy with optional fallback to native execution.

    Wraps every A2A call with a :class:`~ii_agent.integrations.a2a.circuit_breaker.CircuitBreaker`
    so that repeated adapter failures trigger an automatic fallback to the
    native execution path without hammering an unavailable service.

    When a fallback occurs a :class:`~ii_agent.realtime.events.app_events.DelegationFallbackEvent`
    is yielded so callers can forward it through the realtime bus.

    Context reconciliation
    ----------------------
    When ``context_reuse`` is ``True`` (default), each A2A call sends the
    same ``context_id`` derived from the session/run so the CLI can retrieve
    its conversation history.  However, after a native-fallback turn the
    CLI's context diverges from ii-agent's persisted message history.  To
    prevent split-brain state, the loop tracks the last execution owner
    (``"a2a"`` or ``"native"``) via the private ``_last_owner`` field.  On
    the first A2A call after a native-fallback turn the context_id is
    suffixed with a fresh UUID, signalling the CLI to start a clean session
    that will be reconstructed from the canonical database history.
    """

    client: IIAgentA2AClient
    fallback_strategy: InnerLoopStrategy = field(default_factory=NativeInnerLoop)
    fallback_to_native: bool = True
    context_reuse: bool = True
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    tool_router: ToolRoutingLayer = field(default_factory=ToolRoutingLayer)
    # Mutable holder for deferred sandbox binding.  When the strategy is
    # created before a sandbox exists, the factory stores a ``[None]`` list
    # here.  The agent's ``sandbox`` setter later fills ``[0]`` with the
    # real sandbox so the url_factory closure can resolve the adapter port.
    _sandbox_ref: list = field(default_factory=lambda: [None], init=False, repr=False)
    # Internal: tracks which backend served the previous turn.
    # Not exposed as a constructor argument; managed by the loop itself.
    _last_owner: str = field(default="", init=False, repr=False)

    async def aresponse_stream(
        self,
        *,
        model: Model,
        messages: List[Message],
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Union[Function, dict]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        tool_call_limit: Optional[int] = None,
        run_response: Optional[RunOutput] = None,
    ) -> AsyncIterator[Union[ModelResponse, RunOutputEvent]]:
        _ = response_format  # Currently handled by native models; A2A path is tool-first.
        context_id = self._effective_context_id(run_response)
        tool_routing = self._build_tool_routing_metadata(tools or [])

        # Serialize native tools for bridging into the Copilot CLI session.
        native_tool_schemas: List[Dict[str, Any]] = []
        if tools:
            from ii_agent.integrations.a2a.tool_bridge import serialize_tool_schemas

            native_tool_schemas = serialize_tool_schemas(tools)

        # Forward the agent's system message to the adapter so the
        # Copilot CLI LLM receives the same directives (browser rules,
        # personality, capabilities) as the native inner loop.
        system_message_content: Optional[str] = None
        for msg in messages:
            if msg.role in ("system", "developer"):
                system_message_content = msg.content
                break

        metadata: Dict[str, Any] = {
            "model": model.id,
            "tool_call_limit": tool_call_limit,
            "tool_choice": tool_choice,
            "context_reuse": self.context_reuse,
            "tool_count": len(tools or []),
            "tool_routing": tool_routing,
            "native_tool_schemas": native_tool_schemas,
            "system_message": system_message_content,
        }
        logger.info(f"[a2a:stream] model_id={model.id!r} context_id={context_id} source=agent")

        # --- Circuit breaker pre-check ---
        circuit_open_reason: Optional[str] = None
        try:
            await self.circuit_breaker.check()
        except CircuitBreakerOpenError as cb_err:
            circuit_open_reason = str(cb_err)

        if circuit_open_reason is not None:
            # Circuit is open: emit the fallback event and skip A2A entirely.
            self.circuit_breaker.record_fallback()
            yield self._build_fallback_event(
                context_id=context_id,
                reason=circuit_open_reason,
                model_name=getattr(model, "name", model.id),
                run_response=run_response,
            )
            if self.fallback_to_native:
                self._last_owner = "native"
                async for fallback_event in self.fallback_strategy.aresponse_stream(
                    model=model,
                    messages=messages,
                    response_format=response_format,
                    tools=tools,
                    tool_choice=tool_choice,
                    tool_call_limit=tool_call_limit,
                    run_response=run_response,
                ):
                    yield fallback_event
            else:
                raise ModelProviderError(
                    f"A2A circuit breaker open and fallback disabled: {circuit_open_reason}",
                    model_name=getattr(model, "name", model.id),
                    model_id=model.id,
                )
            return

        # --- Main A2A call ---
        # Acquire the per-session compaction lock to prevent native
        # summarization from running while the CLI backend is active.
        #
        # IMPORTANT: lock acquisition and the CompactionAuthorityEvent yield
        # MUST live inside the ``try`` block.  If the consumer calls
        # ``aclose()`` on this generator (e.g. cancellation path) while we
        # are suspended at the yield, Python injects ``GeneratorExit`` at the
        # suspension point.  Any acquire/yield outside the try would skip the
        # ``finally`` block and leak the in-memory asyncio.Lock, deadlocking
        # every subsequent turn on the same session until backend restart.
        session_uuid = getattr(run_response, "session_id", None)
        _lock = None
        _lock_acquired = False
        try:
            if session_uuid is not None:
                from ii_agent.chat.application.compaction_lock import _get_lock

                _lock = _get_lock(session_uuid)
                await _lock.acquire()
                _lock_acquired = True
                # Emit compaction authority telemetry so logs attribute
                # any subsequent compaction to the A2A backend.
                yield CompactionAuthorityEvent(
                    group=EventGroup.AGENT,
                    session_id=session_uuid,
                    run_id=getattr(run_response, "run_id", None),
                    authority="a2a",
                    context_id=context_id,
                    compaction_locked=True,
                    content={"authority": "a2a", "context_id": context_id},
                )
            run_id = getattr(run_response, "run_id", None)
            adapter_task_id: Optional[str] = None

            # Track accumulated delta text and whether a non-delta content
            # finalization was received.  If the stream ends with deltas
            # but no finalization (e.g. ASSISTANT_MESSAGE had empty content),
            # we emit a synthetic non-delta event so the agent persists the
            # accumulated text.
            _accumulated_text = ""
            _content_finalized = False

            # Track reasoning state so we can:
            # 1) Emit "reasoning_started" only for the first delta
            # 2) Synthesize "reasoning_done" when reasoning stops
            _reasoning_active = False
            _accumulated_reasoning = ""

            # Track whether the stream produced ANY meaningful output.
            # When the upstream backend (e.g. Copilot CLI) is quota-blocked,
            # some sessions emit ASSISTANT_TURN_START → ASSISTANT_TURN_END
            # with NO session.error and NO content deltas.  Without this
            # flag the run silently "completes" with an empty assistant
            # response and the user sees nothing on the frontend.
            _tool_call_observed = False

            async for event in self.client.astream(
                messages=messages,
                context_id=context_id,
                metadata=metadata,
            ):
                # Check for cancellation at each event boundary.
                if run_id is not None:
                    await raise_if_cancelled(str(run_id))

                # Heartbeat events keep the HTTP stream alive during long
                # tool executions.  Ignore them here.
                if event.event_type == "heartbeat":
                    logger.debug("A2A inner loop: received heartbeat (connection alive)")
                    continue

                # Capture the adapter task ID for cancel propagation.
                if event.event_type == "session.task_id":
                    adapter_task_id = str(event.data.get("task_id") or "")
                    continue

                # Synthesize reasoning_done when we transition away from
                # reasoning (tool call, content, usage, etc.).
                _is_reasoning_event = event.event_type in {
                    "assistant.reasoning_delta",
                    "reasoning_delta",
                    "assistant.reasoning",
                    "reasoning_done",
                }
                if _reasoning_active and not _is_reasoning_event:
                    yield ModelResponse(
                        reasoning_content=_accumulated_reasoning,
                        is_delta=False,
                        delta_status="reasoning_done",
                    )
                    _reasoning_active = False

                # Handle bridged tool execution requests inline.
                # WARNING: while the tool executes, the SSE read loop is
                # paused — heartbeats from the adapter accumulate in httpx's
                # buffer but are not consumed until execution completes.
                if event.event_type == "tool.execution_request":
                    _tool_call_observed = True
                    _tool_name = event.data.get("tool_name", "?")
                    _tool_t0 = __import__("time").perf_counter()
                    logger.info(
                        "A2A inner loop: starting bridged tool execution '{}' "
                        "(SSE read loop paused)",
                        _tool_name,
                    )
                    async for tool_event in self._handle_tool_execution_request(
                        event.data,
                        tools=tools,
                        context_id=context_id,
                    ):
                        yield tool_event
                    _tool_elapsed = __import__("time").perf_counter() - _tool_t0
                    logger.info(
                        "A2A inner loop: bridged tool '{}' completed in {:.1f}s "
                        "(SSE read loop resuming)",
                        _tool_name,
                        _tool_elapsed,
                    )
                    if _tool_elapsed > 30.0:
                        logger.warning(
                            "A2A inner loop: bridged tool '{}' took {:.1f}s — "
                            "httpx buffer may have accumulated heartbeats",
                            _tool_name,
                            _tool_elapsed,
                        )
                    continue

                mapped = self._map_event(event, reasoning_active=_reasoning_active)
                if mapped is not None:
                    # Track content accumulation for synthetic finalization.
                    if mapped.content and mapped.is_delta:
                        _accumulated_text += mapped.content
                    elif mapped.content and not mapped.is_delta:
                        _content_finalized = True
                        _accumulated_text = mapped.content

                    # Track reasoning accumulation for synthetic finalization.
                    if mapped.reasoning_content and mapped.is_delta:
                        if not _reasoning_active:
                            _reasoning_active = True
                            _accumulated_reasoning = ""
                        _accumulated_reasoning += mapped.reasoning_content
                    elif mapped.delta_status == "reasoning_done":
                        # Explicit reasoning_done from the adapter: finalize
                        # immediately so the synthetic emitter above doesn't
                        # duplicate the event on the next non-reasoning event.
                        _reasoning_active = False

                    yield mapped

            # Synthetic reasoning finalization: if reasoning deltas were
            # streaming but the stream ended without an explicit completion
            # signal, emit a reasoning_done so the agent persists the
            # thinking block.
            if _reasoning_active:
                yield ModelResponse(
                    reasoning_content=_accumulated_reasoning,
                    is_delta=False,
                    delta_status="reasoning_done",
                )
                _reasoning_active = False

            # Synthetic finalization: if streaming deltas accumulated text
            # but ASSISTANT_MESSAGE had empty content (no non-delta event
            # was emitted), yield a final non-delta event so the agent
            # persists the response to the database.
            if _accumulated_text and not _content_finalized:
                yield ModelResponse(
                    content=_accumulated_text,
                    is_delta=False,
                    delta_status="content_done",
                )

            # Append an assistant Message to the messages list so that
            # _finalize_run_response can persist the response to session
            # history.  The native inner-loop path (model.aresponse_stream)
            # does this internally; the A2A path must do it explicitly.
            if _accumulated_text or _accumulated_reasoning:
                assistant_msg = Message(
                    role="assistant",
                    content=_accumulated_text or None,
                    reasoning_content=_accumulated_reasoning or None,
                )
                messages.append(assistant_msg)

            # Defensive: if the upstream backend (e.g. Copilot CLI when
            # quota-blocked) closed the turn without emitting any content,
            # reasoning, tool calls, OR an explicit session.error, surface
            # this as a model-provider error instead of silently completing
            # with an empty assistant response.  Without this, agent.py
            # marks the run COMPLETED, the frontend never receives a
            # response, and the user sees a "silent failure".
            if not _accumulated_text and not _accumulated_reasoning and not _tool_call_observed:
                raise ModelProviderError(
                    "A2A backend closed turn without content (no text, "
                    "reasoning, tool call, or session.error). The upstream "
                    "model provider may be quota-limited or rate-limited. "
                    "Check the sandbox adapter log for SESSION_ERROR events.",
                    model_name=getattr(model, "name", model.id),
                    model_id=model.id,
                )

            await self.circuit_breaker.record_success()
            self._last_owner = "a2a"
        except RunCancelledException:
            # Propagate cancellation to the adapter so it can unblock
            # any waiting tool bridge handlers, then re-raise for
            # agent.py to handle (sets RunStatus.CANCELLED).
            # Persist partial assistant content so session history
            # reflects what was streamed before cancellation.
            if _accumulated_text or _accumulated_reasoning:
                assistant_msg = Message(
                    role="assistant",
                    content=_accumulated_text or None,
                    reasoning_content=_accumulated_reasoning or None,
                )
                messages.append(assistant_msg)
            if adapter_task_id:
                await self.client.cancel_task(adapter_task_id)
            raise
        except Exception as exc:
            await self.circuit_breaker.record_failure(exc)

            # Non-retriable errors (bad prompt, malformed JSON) should not
            # trigger a fallback — they would fail on native too.
            if is_non_retriable(exc):
                raise ModelProviderError(
                    f"A2A non-retriable error: {exc}",
                    model_name=getattr(model, "name", model.id),
                    model_id=model.id,
                ) from exc

            if not self.fallback_to_native:
                raise ModelProviderError(
                    f"A2A inner loop failed without fallback: {exc}",
                    model_name=getattr(model, "name", model.id),
                    model_id=model.id,
                ) from exc

            self.circuit_breaker.record_fallback()
            logger.opt(exception=True).warning(
                "A2A inner loop failed; falling back to native model stream "
                "(circuit breaker failure={}/{})",
                self.circuit_breaker.failure_count,
                self.circuit_breaker.failure_threshold,
            )
            yield self._build_fallback_event(
                context_id=context_id,
                reason=f"A2A stream error: {exc}",
                model_name=getattr(model, "name", model.id),
                run_response=run_response,
            )
            self._last_owner = "native"
            async for fallback_event in self.fallback_strategy.aresponse_stream(
                model=model,
                messages=messages,
                response_format=response_format,
                tools=tools,
                tool_choice=tool_choice,
                tool_call_limit=tool_call_limit,
                run_response=run_response,
            ):
                yield fallback_event
        finally:
            # Only release if we successfully acquired in this call.
            # ``_lock.locked()`` alone is unsafe because the lock may be
            # held by a different task, and calling release() on an
            # unacquired (or foreign-held) asyncio.Lock raises RuntimeError.
            if _lock_acquired and _lock is not None:
                try:
                    _lock.release()
                except RuntimeError:
                    # Defensive: lock state diverged (e.g. already released
                    # by a nested path).  Log and move on -- never let
                    # cleanup errors mask the original exception.
                    logger.warning(
                        f"A2A inner loop: compaction lock release raised RuntimeError "
                        f"(session={session_uuid}) -- treating as released"
                    )

    # ------------------------------------------------------------------
    # Tool bridge: execute bridged tools locally and return results
    # ------------------------------------------------------------------

    async def _handle_tool_execution_request(
        self,
        data: Dict[str, Any],
        *,
        tools: Optional[List[Union[Function, dict]]],
        context_id: str,
    ) -> AsyncIterator[Union[ModelResponse, RunOutputEvent]]:
        """Execute a bridged tool and POST the result to the adapter.

        Called when the event stream contains a ``tool.execution_request``
        event — meaning the Copilot CLI invoked one of the registered
        native tools and is waiting for a result.

        Yields :class:`ModelResponse` events for ``tool_call_started`` and
        ``tool_call_completed`` so the realtime bus can forward them to the
        client exactly as the native path does.
        """
        tool_call_id = str(data.get("tool_call_id", ""))
        tool_name = str(data.get("tool_name", ""))
        arguments = data.get("arguments") or {}

        logger.info(
            "A2A tool bridge: executing bridged tool {} (call={})",
            tool_name,
            tool_call_id,
        )

        result_str, events = await self._execute_bridged_tool(
            tool_name, arguments, tools or [], tool_call_id
        )

        # Yield any tool lifecycle events (started / completed).
        for ev in events:
            yield ev

        # Deliver the result to the adapter so the SDK handler unblocks.
        delivered = await self.client.post_tool_result(
            tool_call_id=tool_call_id,
            result=result_str,
        )
        if not delivered:
            logger.warning(
                "A2A tool bridge: failed to deliver result for {} (call={})",
                tool_name,
                tool_call_id,
            )

    async def _execute_bridged_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tools: List[Union[Function, dict]],
        tool_call_id: str = "",
    ) -> Tuple[str, List[ModelResponse]]:
        """Run the Function entrypoint for a bridged tool via FunctionCall.aexecute().

        This replicates the native execution path:
        - Creates a proper ``FunctionCall`` so ``_build_entrypoint_args`` can
          inject ``agent``, ``run_context``, ``session_state``, ``dependencies``,
          ``fc``, and media fields based on signature inspection.
        - Calls ``aexecute()`` which runs ``pre_hook`` → entrypoint → ``post_hook``
          (including async hooks for sandbox initialization in BaseSandboxTool /
          MCPTool).
        - Emits ``tool_call_started`` and ``tool_call_completed`` ModelResponse
          events for realtime bus forwarding.

        Returns
        -------
        tuple[str, list[ModelResponse]]
            The string result to POST back to the adapter, and a list of
            ModelResponse events (started + completed) to yield upstream.
        """
        events: List[ModelResponse] = []

        # Resolve CLI-native tool aliases to ii-agent tool names.
        # The Copilot CLI has built-in tools (e.g. ``message_user``) that
        # overlap with ii-agent bridged tools (e.g. ``send_user_files``).
        # When the CLI LLM calls its native name, we need to map it to
        # the registered Function name so the bridge can execute it with
        # proper hooks (like file upload in ``on_tool_end``).
        resolved_name = _TOOL_NAME_ALIASES.get(tool_name, tool_name)
        if resolved_name != tool_name:
            logger.info(
                "A2A tool bridge: resolved CLI alias '{}' → '{}'",
                tool_name,
                resolved_name,
            )

        for tool in tools:
            if not isinstance(tool, Function):
                continue
            if tool.name != resolved_name:
                continue
            if tool.entrypoint is None:
                return f"Tool '{tool_name}' has no executable entrypoint", []

            # --- HITL pause check ---
            # Replicate the native model layer's behaviour: if the Function
            # has any human-in-the-loop flags set, emit a ToolCallPaused
            # event instead of executing.  agent.py will set
            # RunStatus.PAUSED and wait for user confirmation/input.
            paused_executions: List[ToolExecution] = []
            if tool.requires_confirmation:
                paused_executions.append(
                    ToolExecution(
                        tool_call_id=tool_call_id or str(uuid.uuid4()),
                        tool_name=tool.name,
                        tool_args=arguments,
                        display_name=tool.display_name,
                        tool_logo=tool.tool_logo,
                        requires_confirmation=True,
                    )
                )
            if tool.requires_user_input:
                paused_executions.append(
                    ToolExecution(
                        tool_call_id=tool_call_id or str(uuid.uuid4()),
                        tool_name=tool.name,
                        tool_args=arguments,
                        display_name=tool.display_name,
                        tool_logo=tool.tool_logo,
                        requires_user_input=True,
                        user_input_schema=tool.user_input_schema,
                    )
                )
            if tool.external_execution:
                paused_executions.append(
                    ToolExecution(
                        tool_call_id=tool_call_id or str(uuid.uuid4()),
                        tool_name=tool.name,
                        tool_args=arguments,
                        display_name=tool.display_name,
                        tool_logo=tool.tool_logo,
                        external_execution_required=True,
                    )
                )
            if paused_executions:
                logger.info(
                    "A2A tool bridge: tool '{}' requires HITL — emitting ToolCallPaused (call={})",
                    tool_name,
                    tool_call_id,
                )
                pause_event = ModelResponse(
                    tool_executions=paused_executions,
                    event=ModelResponseEvent.tool_call_paused.value,
                )
                return (
                    f"Tool '{tool_name}' requires human approval and cannot "
                    "be auto-executed via A2A bridge",
                    [pause_event],
                )

            # Build a FunctionCall the same way the native path does.
            fc = FunctionCall(
                function=tool,
                arguments=arguments or None,
                call_id=tool_call_id or str(uuid.uuid4()),
            )

            # --- tool_call_started event ---
            events.append(
                ModelResponse(
                    content=fc.get_call_str(),
                    tool_executions=[
                        ToolExecution(
                            tool_call_id=fc.call_id,
                            tool_name=tool.name,
                            tool_args=arguments,
                            display_name=tool.display_name,
                            tool_logo=tool.tool_logo,
                        )
                    ],
                    event=ModelResponseEvent.tool_call_started.value,
                )
            )

            timer_start = perf_counter()
            try:
                execution_result: FunctionExecutionResult = await fc.aexecute()
            except AgentRunException as exc:
                elapsed = perf_counter() - timer_start
                error_msg = str(exc)
                events.append(
                    self._build_tool_completed_event(
                        fc,
                        result_str=error_msg,
                        error=True,
                        elapsed=elapsed,
                        execution_result=FunctionExecutionResult(status="failure", error=error_msg),
                    )
                )
                logger.warning(
                    "Bridged tool '{}' raised AgentRunException: {}",
                    tool_name,
                    exc,
                )
                return f"Error executing tool '{tool_name}': {exc}", events
            except Exception as exc:
                elapsed = perf_counter() - timer_start
                error_msg = str(exc)
                events.append(
                    self._build_tool_completed_event(
                        fc,
                        result_str=error_msg,
                        error=True,
                        elapsed=elapsed,
                        execution_result=FunctionExecutionResult(status="failure", error=error_msg),
                    )
                )
                logger.opt(exception=True).error(
                    "Bridged tool '{}' execution failed: {}",
                    tool_name,
                    exc,
                )
                return f"Error executing tool '{tool_name}': {exc}", events

            elapsed = perf_counter() - timer_start

            # Extract the string result to send back to the CLI.
            result_str = self._extract_result_string(execution_result)

            # --- tool_call_completed event ---
            events.append(
                self._build_tool_completed_event(
                    fc,
                    result_str=result_str,
                    error=execution_result.status != "success",
                    elapsed=elapsed,
                    execution_result=execution_result,
                )
            )

            return result_str, events

        return f"Tool '{tool_name}' not found in agent tool set", []

    @staticmethod
    def _extract_result_string(execution_result: FunctionExecutionResult) -> str:
        """Extract a string representation from a FunctionExecutionResult."""
        if execution_result.status != "success":
            return execution_result.error or "Unknown error"

        result = execution_result.result
        if result is None:
            return ""

        # Handle BaseToolResult (from BaseAgentTool — has llm_content).
        from ii_agent.agents.tools.base import ToolResult as BaseToolResult
        from ii_agent.agents.tools.function import ToolResult as FunctionToolResult

        if isinstance(result, BaseToolResult):
            llm_content = result.llm_content
            if isinstance(llm_content, str):
                return llm_content
            if isinstance(llm_content, list):
                parts = [getattr(c, "text", str(c)) for c in llm_content]
                return "\n".join(parts) if parts else ""
            return str(llm_content)

        # Handle ToolResult from function.py (legacy — has content field).
        if isinstance(result, FunctionToolResult):
            return result.content

        return str(result)

    @staticmethod
    def _build_tool_completed_event(
        fc: FunctionCall,
        *,
        result_str: str,
        error: bool,
        elapsed: float,
        execution_result: FunctionExecutionResult,
    ) -> ModelResponse:
        """Build a ``tool_call_completed`` ModelResponse.

        When the execution result contains a ``BaseToolResult`` (from tools
        that use ``user_display_content`` for rich frontend payloads, e.g.
        ``send_user_files``), the full object is stored in
        ``ToolExecution.result`` so the event converter can extract
        ``user_display_content`` — matching the native execution path.
        Without this, post-hooks like ``on_tool_end`` that upload sandbox
        files to persistent storage and write permanent URLs into
        ``user_display_content`` would have their work silently discarded.
        """
        from ii_agent.agents.tools.base import ToolResult as BaseToolResult

        # Use the full BaseToolResult when available so the event converter
        # can extract user_display_content (e.g. uploaded attachment URLs).
        # This matches the native path where FunctionCall.result stores the
        # raw ToolResult object.
        display_result: object = result_str
        if (
            not error
            and execution_result.result is not None
            and isinstance(execution_result.result, BaseToolResult)
        ):
            display_result = execution_result.result

        return ModelResponse(
            content=f"{fc.get_call_str()} completed in {elapsed:.4f}s. ",
            tool_executions=[
                ToolExecution(
                    tool_call_id=fc.call_id,
                    tool_name=fc.function.name,
                    tool_args=fc.arguments,
                    tool_call_error=error or None,
                    result=display_result,
                    display_name=fc.function.display_name,
                    tool_logo=fc.function.tool_logo,
                    sandbox=fc.get_sandbox_info(),
                )
            ],
            event=ModelResponseEvent.tool_call_completed.value,
            updated_session_state=execution_result.updated_session_state,
            images=execution_result.images,
            videos=execution_result.videos,
            audios=execution_result.audios,
            files=execution_result.files,
        )

    def _build_tool_routing_metadata(
        self,
        tools: List[Union[Function, dict]],
    ) -> dict[str, str]:
        """Classify each tool by routing owner using :class:`ToolRoutingLayer`.

        Returns a ``{tool_name: owner}`` mapping included in the A2A request
        metadata so the adapter (and any log consumer) can inspect routing
        decisions.  Security-sensitive tools trigger a warning because they
        should never leave the server boundary even when a turn is A2A-delegated.
        """
        routing: dict[str, str] = {}
        for tool in tools:
            name: str
            if isinstance(tool, dict):
                name = str(tool.get("name") or "unknown")
            else:
                name = getattr(tool, "name", "unknown")
            decision = self.tool_router.route(name)
            routing[name] = decision.owner.value
            if name in self.tool_router.SECURITY_SENSITIVE_TOOLS:
                logger.warning(
                    "Security-sensitive tool '{}' is present in an A2A-delegated turn; "
                    "this tool must only be executed server-side, never by the CLI backend.",
                    name,
                )
        return routing

    def _effective_context_id(self, run_response: Optional[RunOutput]) -> str:
        """Return the context ID to use for the A2A call.

        After a native-fallback turn, the CLI's context history has diverged
        from ii-agent's canonical message history.  To reconcile, we start
        a fresh context (suffixed with a new UUID) so the CLI initialises a
        clean session rather than continuing from stale state.

        On the first-ever call (``_last_owner`` is empty) or when
        ``context_reuse`` is disabled, a plain canonical context ID is used.
        """
        canonical = self._resolve_context_id(run_response)
        if not self.context_reuse:
            return canonical
        if self._last_owner == "native":
            # Previous turn was served natively; CLI context is stale.
            # Append a sub-key that signals a fresh session.
            fresh_suffix = str(uuid.uuid4())[:8]
            logger.info(
                "A2A context reconciliation: last turn was native; "
                "starting fresh CLI session (context={}.reconcile.{})",
                canonical,
                fresh_suffix,
            )
            return f"{canonical}.reconcile.{fresh_suffix}"
        return canonical

    @staticmethod
    def _resolve_context_id(run_response: Optional[RunOutput]) -> str:
        if run_response is None:
            return "default"
        if getattr(run_response, "session_id", None):
            return str(run_response.session_id)
        if getattr(run_response, "run_id", None):
            return str(run_response.run_id)
        return "default"

    def _build_fallback_event(
        self,
        *,
        context_id: str,
        reason: str,
        model_name: str,
        run_response: Optional[RunOutput],
    ) -> DelegationFallbackEvent:
        """Construct a :class:`DelegationFallbackEvent` from current circuit state."""
        return DelegationFallbackEvent(
            group=EventGroup.AGENT,
            session_id=getattr(run_response, "session_id", None),
            run_id=getattr(run_response, "run_id", None),
            reason=reason,
            context_id=context_id,
            circuit_state=self.circuit_breaker.state.value,
            failure_count=self.circuit_breaker.failure_count,
            cooldown_remaining=self.circuit_breaker.remaining_cooldown(),
            content={"model": model_name, "reason": reason},
        )

    @staticmethod
    def _map_event(
        event: A2AStreamEvent,
        reasoning_active: bool = False,
    ) -> Optional[ModelResponse]:
        event_type = event.event_type
        data = event.data

        if event_type in {"assistant.message_delta", "text_delta", "message_delta"}:
            delta = str(data.get("delta") or data.get("text") or "")
            if not delta:
                return None
            return ModelResponse(content=delta, is_delta=True, delta_status="content_started")

        if event_type in {"assistant.reasoning_delta", "reasoning_delta"}:
            delta = str(data.get("delta") or data.get("text") or "")
            if not delta:
                return None
            # Only the first reasoning delta in a cycle should carry
            # "reasoning_started"; subsequent deltas use None so the
            # agent accumulates content without resetting each time.
            status = "reasoning_started" if not reasoning_active else None
            return ModelResponse(
                reasoning_content=delta,
                is_delta=True,
                delta_status=status,
            )

        if event_type in {"assistant.reasoning", "reasoning_done"}:
            content = str(data.get("content") or data.get("text") or "")
            if not content:
                return None
            # Use is_delta=False to match native Anthropic behaviour —
            # the reasoning deltas already accumulated the full text, and
            # the completion event should finalise (replace) rather than
            # append again (which caused doubled reasoning content).
            return ModelResponse(
                reasoning_content=content,
                is_delta=False,
                delta_status="reasoning_done",
            )

        if event_type in {"assistant.message", "message_complete", "content_done"}:
            content = str(data.get("content") or data.get("text") or "")
            tool_calls = data.get("tool_calls")
            if isinstance(tool_calls, list) and not tool_calls:
                tool_calls = None
            elif not isinstance(tool_calls, list):
                tool_calls = None
            # When the SDK streams deltas (ASSISTANT_MESSAGE_DELTA) followed
            # by a final ASSISTANT_MESSAGE, the final event may carry empty
            # content — it's just an end-of-turn signal.  Returning a
            # non-delta ModelResponse with content="" would replace the
            # accumulated delta text with an empty string, blanking both the
            # live UI and the persisted response.
            #
            # Only emit a non-delta content replacement when the final event
            # actually carries content or tool_calls.  For empty-content
            # events we return None and let the synthetic finalization in
            # aresponse_stream handle persistence.
            if not content and not tool_calls:
                return None
            # Use is_delta=False so the agent replaces accumulated content
            # instead of appending the full text again (which caused
            # duplicate/stuttered output in the UI).
            return ModelResponse(
                content=content,
                tool_calls=tool_calls or [],
                is_delta=False,
                delta_status="content_done",
            )

        if event_type in {"assistant.usage", "usage"}:
            metrics = Metrics(
                input_tokens=int(data.get("input_tokens") or 0),
                output_tokens=int(data.get("output_tokens") or 0),
                total_tokens=int(data.get("total_tokens") or 0),
                cache_read_tokens=int(data.get("cache_read_tokens") or 0),
                cache_write_tokens=int(data.get("cache_write_tokens") or 0),
                reasoning_tokens=int(data.get("reasoning_tokens") or 0),
                cost=float(data.get("cost") or 0.0),
                billing_backend=f"a2a:{data.get('backend') or 'unknown'}",
                premium_requests=int(data.get("premium_requests") or 0),
                duration=float(data.get("duration") or 0.0) or None,
            )
            return ModelResponse(response_usage=metrics, is_delta=True)

        if event_type in {"session.error", "error"}:
            message = str(data.get("message") or "Unknown A2A stream error")
            raise ModelProviderError(message)

        return None
