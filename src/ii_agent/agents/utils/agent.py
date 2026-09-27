from asyncio import Future, Task
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Union,
)

from ii_agent.files.media import Audio, File, Image, Video
from ii_agent.agents.models.message import Message
from ii_agent.agents.models.response import ModelResponse
from ii_agent.agents.runs import RunContext
from ii_agent.agents.runs.agent import RunEvent, RunInput, RunOutput, RunOutputEvent
from ii_agent.agents.sessions import AgentSession
from ii_agent.core.logger import logger
from ii_agent.agents.runs.events import (
    create_memory_update_completed_event,
    create_memory_update_started_event,
    handle_event,
)


if TYPE_CHECKING:
    from ii_agent.agents.agent import Agent

# Constants for tool execution abort/error messages
DEFAULT_ABORT_REASON = "Run was aborted by user"


def get_tool_abort_message(reason: str = "") -> str:
    """Get the formatted message for a tool execution abort.

    Args:
        reason: The reason for the abort. If empty, uses default reason.

    Returns:
        Formatted abort message string.
    """
    abort_reason = reason if reason else DEFAULT_ABORT_REASON
    return (
        f"[TOOL EXECUTION ABORTED]\n"
        f"Status: Cancelled\n"
        f"Reason: {abort_reason}\n"
        f"Note: This tool was not executed because the run was aborted before completion."
    )


def get_tool_error_message(error: str) -> str:
    """Get the formatted message for a tool execution error.

    Args:
        error: The error message/description.

    Returns:
        Formatted error message string.
    """
    return (
        f"[TOOL EXECUTION FAILED]\n"
        f"Status: Error\n"
        f"Error: {error}\n"
        f"Note: This tool was not executed due to a system error during the run."
    )


async def await_for_thread_tasks_stream(
    run_response: RunOutput,
    memory_task: Optional[Task] = None,
    cultural_knowledge_task: Optional[Task] = None,
    stream_events: bool = False,
    events_to_skip: Optional[List[RunEvent]] = None,
    store_events: bool = False,
) -> AsyncIterator[RunOutputEvent]:
    if memory_task is not None:
        if stream_events:
            yield handle_event(  # type: ignore
                create_memory_update_started_event(from_run_response=run_response),
                run_response,
                events_to_skip=events_to_skip,  # type: ignore
                store_events=store_events,
            )
        try:
            await memory_task
        except Exception as e:
            logger.warning(f"Error in memory creation: {str(e)}")
        if stream_events:
            yield handle_event(  # type: ignore
                create_memory_update_completed_event(from_run_response=run_response),
                run_response,
                events_to_skip=events_to_skip,  # type: ignore
                store_events=store_events,
            )

    if cultural_knowledge_task is not None:
        try:
            await cultural_knowledge_task
        except Exception as e:
            logger.warning(f"Error in cultural knowledge creation: {str(e)}")


def wait_for_thread_tasks_stream(
    run_response: RunOutput,
    memory_future: Optional[Future] = None,
    cultural_knowledge_future: Optional[Future] = None,
    stream_events: bool = False,
    events_to_skip: Optional[List[RunEvent]] = None,
    store_events: bool = False,
) -> Iterator[RunOutputEvent]:
    if memory_future is not None:
        if stream_events:
            yield handle_event(  # type: ignore
                create_memory_update_started_event(from_run_response=run_response),
                run_response,
                events_to_skip=events_to_skip,  # type: ignore
                store_events=store_events,
            )
        try:
            memory_future.result()
        except Exception as e:
            logger.warning(f"Error in memory creation: {str(e)}")
        if stream_events:
            yield handle_event(  # type: ignore
                create_memory_update_completed_event(from_run_response=run_response),
                run_response,
                events_to_skip=events_to_skip,  # type: ignore
                store_events=store_events,
            )

    # Wait for cultural knowledge creation
    if cultural_knowledge_future is not None:
        # TODO: Add events
        try:
            cultural_knowledge_future.result()
        except Exception as e:
            logger.warning(f"Error in cultural knowledge creation: {str(e)}")


def expire_historical_images(messages: List[Message], retention_turns: int) -> None:
    """Remove expired user images from a copy of model-facing history."""
    remaining_turns = retention_turns
    for message in reversed(messages):
        if message.role != "user":
            continue
        if remaining_turns == 0:
            message.images = None
        else:
            remaining_turns -= 1


def collect_joint_images(
    run_input: Optional[RunInput] = None,
    session: Optional[AgentSession] = None,
) -> Optional[Sequence[Image]]:
    """Collect images from input, session history, and current run response."""
    joint_images: List[Image] = []

    # 1. Add images from current input
    if run_input and run_input.images:
        joint_images.extend(run_input.images)
        logger.debug(f"Added {len(run_input.images)} input images to joint list")

    # 2. Add images from recent session runs (from both input and generated sources)
    try:
        if session and session.runs:
            from ii_agent.core.config.settings import get_settings

            retention_turns = get_settings().agent.image_retention_turns
            for historical_run in session.runs[-retention_turns:] if retention_turns else []:
                # Add generated images from previous runs
                if historical_run.images:
                    joint_images.extend(historical_run.images)
                    logger.debug(
                        f"Added {len(historical_run.images)} generated images from historical run {historical_run.run_id}"
                    )

                # Add input images from previous runs
                if historical_run.input and historical_run.input.images:
                    joint_images.extend(historical_run.input.images)
                    logger.debug(
                        f"Added {len(historical_run.input.images)} input images from historical run {historical_run.run_id}"
                    )
    except Exception as e:
        logger.debug(f"Could not access session history for images: {e}")

    if joint_images:
        logger.debug(f"Images Available to Model: {len(joint_images)} images")
    return joint_images if joint_images else None


def collect_joint_videos(
    run_input: Optional[RunInput] = None,
    session: Optional[AgentSession] = None,
) -> Optional[Sequence[Video]]:
    """Collect videos from input, session history, and current run response."""
    joint_videos: List[Video] = []

    # 1. Add videos from current input
    if run_input and run_input.videos:
        joint_videos.extend(run_input.videos)
        logger.debug(f"Added {len(run_input.videos)} input videos to joint list")

    # 2. Add videos from session history (from both input and generated sources)
    try:
        if session and session.runs:
            for historical_run in session.runs:
                # Add generated videos from previous runs
                if historical_run.videos:
                    joint_videos.extend(historical_run.videos)
                    logger.debug(
                        f"Added {len(historical_run.videos)} generated videos from historical run {historical_run.run_id}"
                    )

                # Add input videos from previous runs
                if historical_run.input and historical_run.input.videos:
                    joint_videos.extend(historical_run.input.videos)
                    logger.debug(
                        f"Added {len(historical_run.input.videos)} input videos from historical run {historical_run.run_id}"
                    )
    except Exception as e:
        logger.debug(f"Could not access session history for videos: {e}")

    if joint_videos:
        logger.debug(f"Videos Available to Model: {len(joint_videos)} videos")
    return joint_videos if joint_videos else None


def collect_joint_audios(
    run_input: Optional[RunInput] = None,
    session: Optional[AgentSession] = None,
) -> Optional[Sequence[Audio]]:
    """Collect audios from input, session history, and current run response."""
    joint_audios: List[Audio] = []

    # 1. Add audios from current input
    if run_input and run_input.audios:
        joint_audios.extend(run_input.audios)
        logger.debug(f"Added {len(run_input.audios)} input audios to joint list")

    # 2. Add audios from session history (from both input and generated sources)
    try:
        if session and session.runs:
            for historical_run in session.runs:
                # Add generated audios from previous runs
                if historical_run.audio:
                    joint_audios.extend(historical_run.audio)
                    logger.debug(
                        f"Added {len(historical_run.audio)} generated audios from historical run {historical_run.run_id}"
                    )

                # Add input audios from previous runs
                if historical_run.input and historical_run.input.audios:
                    joint_audios.extend(historical_run.input.audios)
                    logger.debug(
                        f"Added {len(historical_run.input.audios)} input audios from historical run {historical_run.run_id}"
                    )
    except Exception as e:
        logger.debug(f"Could not access session history for audios: {e}")

    if joint_audios:
        logger.debug(f"Audios Available to Model: {len(joint_audios)} audios")
    return joint_audios if joint_audios else None


def collect_joint_files(
    run_input: Optional[RunInput] = None,
) -> Optional[Sequence[File]]:
    """Collect files from input and session history."""

    joint_files: List[File] = []

    # 1. Add files from current input
    if run_input and run_input.files:
        joint_files.extend(run_input.files)

    # TODO: Files aren't stored in session history yet and dont have a FileArtifact

    if joint_files:
        logger.debug(f"Files Available to Model: {len(joint_files)} files")

    return joint_files if joint_files else None


def store_media_util(run_response: RunOutput, model_response: ModelResponse):
    """Store media from model response in run_response for persistence"""
    # Handle generated media fields from ModelResponse (generated media)
    if model_response.images is not None:
        for image in model_response.images:
            if run_response.images is None:
                run_response.images = []
            run_response.images.append(image)  # Generated images go to run_response.images

    if model_response.videos is not None:
        for video in model_response.videos:
            if run_response.videos is None:
                run_response.videos = []
            run_response.videos.append(video)  # Generated videos go to run_response.videos

    if model_response.audios is not None:
        for audio in model_response.audios:
            if run_response.audio is None:
                run_response.audio = []
            run_response.audio.append(audio)  # Generated audio go to run_response.audio

    if model_response.files is not None:
        for file in model_response.files:
            if run_response.files is None:
                run_response.files = []
            run_response.files.append(file)  # Generated files go to run_response.files


def validate_media_object_id(
    images: Optional[Sequence[Image]] = None,
    videos: Optional[Sequence[Video]] = None,
    audios: Optional[Sequence[Audio]] = None,
    files: Optional[Sequence[File]] = None,
) -> tuple:
    image_list = None
    if images:
        image_list = []
        for img in images:
            if not img.id:
                from uuid import uuid4

                img.id = str(uuid4())
            image_list.append(img)

    video_list = None
    if videos:
        video_list = []
        for vid in videos:
            if not vid.id:
                from uuid import uuid4

                vid.id = str(uuid4())
            video_list.append(vid)

    audio_list = None
    if audios:
        audio_list = []
        for aud in audios:
            if not aud.id:
                from uuid import uuid4

                aud.id = str(uuid4())
            audio_list.append(aud)

    file_list = None
    if files:
        file_list = []
        for file in files:
            if not file.id:
                from uuid import uuid4

                file.id = str(uuid4())
            file_list.append(file)

    return image_list, video_list, audio_list, file_list


def scrub_media_from_run_output(run_response: RunOutput) -> None:
    """
    Completely remove all media from RunOutput when store_media=False.
    This includes media in input, output artifacts, and all messages.
    """
    # 1. Scrub RunInput media
    if run_response.input is not None:
        run_response.input.images = []
        run_response.input.videos = []
        run_response.input.audios = []
        run_response.input.files = []

    # 3. Scrub media from all messages
    if run_response.messages:
        for message in run_response.messages:
            scrub_media_from_message(message)

    # 4. Scrub media from additional_input messages if any
    if run_response.additional_input:
        for message in run_response.additional_input:
            scrub_media_from_message(message)

    # 5. Scrub media from reasoning_messages if any
    if run_response.reasoning_messages:
        for message in run_response.reasoning_messages:
            scrub_media_from_message(message)


def scrub_media_from_message(message: Message) -> None:
    """Remove all media from a Message object."""
    # Input media
    message.images = None
    message.videos = None
    message.audio = None
    message.files = None

    # Output media
    message.audio_output = None
    message.image_output = None
    message.video_output = None


def scrub_tool_results_from_run_output(run_response: RunOutput) -> None:
    """
    Remove all tool-related data from RunOutput when store_tool_messages=False.
    This removes both the tool call and its corresponding result to maintain API consistency.
    """
    if not run_response.messages:
        return

    # Step 1: Collect all tool_call_ids from tool result messages
    tool_call_ids_to_remove = set()
    for message in run_response.messages:
        if message.role == "tool" and message.tool_call_id:
            tool_call_ids_to_remove.add(message.tool_call_id)

    # Step 2: Remove tool result messages (role="tool")
    run_response.messages = [msg for msg in run_response.messages if msg.role != "tool"]

    # Step 3: Remove assistant messages that made those tool calls
    filtered_messages = []
    for message in run_response.messages:
        # Check if this assistant message made any of the tool calls we're removing
        should_remove = False
        if message.role == "assistant" and message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.get("id") in tool_call_ids_to_remove:
                    should_remove = True
                    break

        if not should_remove:
            filtered_messages.append(message)

    run_response.messages = filtered_messages


def scrub_history_messages_from_run_output(run_response: RunOutput) -> None:
    """
    Remove all history messages from RunOutput when store_history_messages=False.
    This removes messages that were loaded from the agent's memory.
    """
    # Remove messages with from_history=True
    if run_response.messages:
        run_response.messages = [msg for msg in run_response.messages if not msg.from_history]


def execute_instructions(
    instructions: Callable,
    agent: Optional["Agent"] = None,
    session_state: Optional[Dict[str, Any]] = None,
    run_context: Optional[RunContext] = None,
) -> Union[str, List[str]]:
    """Execute the instructions function."""
    import inspect

    signature = inspect.signature(instructions)
    instruction_args: Dict[str, Any] = {}

    # Check for agent parameter
    if "agent" in signature.parameters:
        instruction_args["agent"] = agent

    # Check for session_state parameter
    if "session_state" in signature.parameters:
        instruction_args["session_state"] = session_state if session_state is not None else {}

    # Check for run_context parameter
    if "run_context" in signature.parameters:
        instruction_args["run_context"] = run_context or None

    # Run the instructions function, await if it's awaitable, otherwise run directly (in thread)
    if inspect.iscoroutinefunction(instructions):
        raise Exception("Instructions function is async, use `agent.arun()` instead")

    # Run the instructions function
    return instructions(**instruction_args)


async def aexecute_instructions(
    instructions: Callable,
    agent: Optional["Agent"] = None,
    session_state: Optional[Dict[str, Any]] = None,
    run_context: Optional[RunContext] = None,
) -> Union[str, List[str]]:
    """Execute the instructions function."""
    import inspect

    signature = inspect.signature(instructions)
    instruction_args: Dict[str, Any] = {}

    # Check for agent parameter
    if "agent" in signature.parameters:
        instruction_args["agent"] = agent

    # Check for session_state parameter
    if "session_state" in signature.parameters:
        instruction_args["session_state"] = session_state if session_state is not None else {}

    # Check for run_context parameter
    if "run_context" in signature.parameters:
        instruction_args["run_context"] = run_context or None

    if inspect.iscoroutinefunction(instructions):
        return await instructions(**instruction_args)
    else:
        return instructions(**instruction_args)


async def aexecute_system_message(system_message: Callable, agent: Optional["Agent"] = None) -> str:
    import inspect

    signature = inspect.signature(system_message)
    system_message_args: Dict[str, Any] = {}

    # Check for agent parameter
    if "agent" in signature.parameters:
        system_message_args["agent"] = agent

    if inspect.iscoroutinefunction(system_message):
        return await system_message(**system_message_args)
    else:
        return system_message(**system_message_args)
