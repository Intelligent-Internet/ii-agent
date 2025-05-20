import hashlib
from pathlib import Path
import re
from ii_agent.llm.base import GeneralContentBlock, ToolFormattedResult, ToolCall
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.token_counter import TokenCounter
import logging
import os
from termcolor import colored
import copy
from ii_agent.tools import TOOLS_NEED_INPUT_TRUNCATION, TOOLS_NEED_OUTPUT_FILE_SAVE
from ii_agent.tools.deep_research_tool import DeepResearchTool
from ii_agent.tools.visit_webpage_tool import VisitWebpageTool
from ii_agent.utils.workspace_manager import WorkspaceManager

HASH_LENGTH = 10


class FileBasedContextManager(ContextManager):
    TRUNCATED_TOOL_OUTPUT_MSG = (
        "[Truncated...re-run tool if you need to see output again.]"
    )
    TRUNCATED_TOOL_INPUT_MSG = (
        "[Truncated...re-run tool if you need to see input/output again.]"
    )
    TRUNCATED_FILE_MSG = (
        "[Truncated...content saved to {relative_path}. You can view it if needed.]"
    )

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        token_counter: TokenCounter,
        logger: logging.Logger,
        token_budget: int = 120_000,
        truncate_keep_n_turns: int = 3,
        min_length_to_truncate: int = 1499,
    ):
        """
        Args:
            workspace_dir: The directory to save truncated content to.
            token_counter: The token counter to use.
            logger: The logger to use.
            token_budget: The token budget to use.
            truncate_keep_n_turns: The number of turns to keep.
            min_length_to_truncate: The minimum length of content to apply truncation to. Don't set this too low.
        """
        super().__init__(token_counter, logger, token_budget)
        self.hash_map = {}
        self.workspace_manager = workspace_manager
        self.agent_memory_dir = workspace_manager.workspace_path(Path("agent_memory"))
        self.truncate_keep_n_turns = truncate_keep_n_turns
        self.min_length_to_truncate = min_length_to_truncate
        os.makedirs(self.agent_memory_dir, exist_ok=True)
        assert self.min_length_to_truncate > len(self.TRUNCATED_FILE_MSG.split(" ")), (
            "min_length_to_truncate must be greater than the length of the truncated file message"
        )
        self.logger.info(f"Agent memory will be saved to {self.agent_memory_dir}")

    def _sanitize_for_filename(self, text: str, max_len: int = 30) -> str:
        """Removes unsafe characters and shortens text for filenames."""
        if not text:
            return ""
        # Remove non-alphanumeric characters (allow underscore and hyphen)
        sanitized = re.sub(r"[^\w\-]+", "_", text)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")
        # Limit length
        return sanitized[:max_len]

    def _get_content_hash(self, content: str) -> str:
        """Computes SHA-256 hash and returns a truncated hex digest."""
        hasher = hashlib.sha256()
        hasher.update(content.encode("utf-8"))
        return hasher.hexdigest()[:HASH_LENGTH]

    def apply_truncation_if_needed(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Applies truncation strategy if token count exceeds budget."""
        current_tokens = self.count_tokens(message_lists)
        if current_tokens <= self._token_budget:
            return message_lists  # No truncation needed

        self.logger.warning(
            f"Token count {current_tokens} exceeds budget {self._token_budget}. "
            f"Truncating history, keeping last {self.truncate_keep_n_turns} turns."
        )
        print(
            colored(
                f"Token count {current_tokens} exceeds budget {self._token_budget}. "
                f"Truncating history, keeping last {self.truncate_keep_n_turns} turns.",
                "yellow",
            )
        )

        # Make a deep copy to modify
        truncated_message_lists = copy.deepcopy(message_lists)

        truncation_point = len(truncated_message_lists) - self.truncate_keep_n_turns

        # Apply file-based truncation to older turns
        for turn_idx, turn in enumerate(truncated_message_lists[:truncation_point]):
            for message in turn:
                if isinstance(message, ToolFormattedResult):
                    # Check if content is long enough to truncate
                    if (
                        self.token_counter.count_tokens(message.tool_output)
                        >= self.min_length_to_truncate
                    ):
                        if message.tool_name in TOOLS_NEED_OUTPUT_FILE_SAVE:
                            # For tools in the list, save to file
                            content_hash = self._get_content_hash(message.tool_output)
                            if message.tool_name == VisitWebpageTool.name:
                                # NOTE: assume that the previous message is a tool call
                                previous_message = truncated_message_lists[
                                    turn_idx - 1
                                ][0]
                                if isinstance(previous_message, ToolCall):
                                    url = previous_message.tool_input.get(
                                        "url", "unknown_url"
                                    )
                                else:
                                    url = "unknown_url"
                                    print(
                                        f"Previous message is not a tool call: {previous_message}"
                                    )
                                filename = self._generate_filename_from_url(
                                    url, content_hash
                                )
                            elif message.tool_name == DeepResearchTool.name:
                                # NOTE: assume that the previous message is a tool call
                                query = truncated_message_lists[turn_idx - 1][
                                    0
                                ].tool_input.get("query", "unknown_query")
                                sanitized_query = self._sanitize_for_filename(query)
                                filename = f"{sanitized_query}_{content_hash}.txt"
                            else:
                                filename = f"{message.tool_name}_{content_hash}.txt"
                            filepath = os.path.join(self.agent_memory_dir, filename)

                            # Only save if content is long enough and file doesn't exist
                            if self.token_counter.count_tokens(
                                message.tool_output
                            ) >= self.min_length_to_truncate and not os.path.exists(
                                filepath
                            ):
                                # Save content to file
                                with open(filepath, "w") as f:
                                    f.write(message.tool_output)

                            # Update message with reference to file
                            message.tool_output = self.TRUNCATED_FILE_MSG.format(
                                relative_path=self.workspace_manager.relative_path(
                                    filepath
                                ),
                            )
                            self.logger.info(f"Saved {filename} to {filepath}")
                        else:
                            # For other tools, use simple truncation if content is long enough
                            if (
                                self.token_counter.count_tokens(message.tool_output)
                                >= self.min_length_to_truncate
                            ):
                                message.tool_output = self.TRUNCATED_TOOL_OUTPUT_MSG

                elif isinstance(message, ToolCall):
                    if message.tool_name in TOOLS_NEED_INPUT_TRUNCATION:
                        # Check if any field exceeds the token limit
                        should_truncate_all = False
                        for field in TOOLS_NEED_INPUT_TRUNCATION[message.tool_name]:
                            if field in message.tool_input:
                                field_value = str(message.tool_input[field])
                                if (
                                    self.token_counter.count_tokens(field_value)
                                    >= self.min_length_to_truncate
                                ):
                                    should_truncate_all = True
                                    break

                        # If any field exceeds the limit, truncate all fields
                        if should_truncate_all:
                            for field in TOOLS_NEED_INPUT_TRUNCATION[message.tool_name]:
                                if field in message.tool_input:
                                    message.tool_input[field] = (
                                        self.TRUNCATED_TOOL_INPUT_MSG
                                    )

        new_token_count = self.count_tokens(truncated_message_lists)
        tokens_saved = current_tokens - new_token_count
        self.logger.info(
            f"Truncation saved ~{tokens_saved} tokens. New count: {new_token_count}"
        )
        print(
            colored(
                f" [ContextManager] Token count after truncation: {new_token_count}",
                "yellow",
            )
        )

        return truncated_message_lists

    def _generate_filename_from_url(self, url: str, content_hash: str) -> str:
        """Generates a filename based on URL and content hash."""
        # Extract domain and path from URL
        url_parts = re.sub(r"^https?://", "", url).split("/")
        domain = url_parts[0]
        path = "_".join(url_parts[1:]) if len(url_parts) > 1 else ""

        # Sanitize and limit length
        domain = self._sanitize_for_filename(domain, max_len=20)
        path = self._sanitize_for_filename(path, max_len=30)

        # Construct filename: domain_path_hash.txt
        filename = f"{domain}"
        if path:
            filename += f"_{path}"
        filename += f"_{content_hash}.txt"

        return filename
