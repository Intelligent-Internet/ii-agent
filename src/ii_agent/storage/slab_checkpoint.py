"""Slab checkpoint system - checkpoint without eviction."""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path

from ii_agent.llm.base import (
    GeneralContentBlock,
    ToolCall,
    ToolFormattedResult,
    TextPrompt,
    TextResult,
    ThinkingBlock,
)
from ii_agent.storage.memvid import MemvidStorage
from ii_agent.storage.hashtable import LRUHashtable
from ii_agent.core.logger import logger


class SlabCheckpoint:
    """Manages slab checkpoints without evicting active context."""

    def __init__(
        self,
        memvid: Optional[MemvidStorage] = None,
        hashtable: Optional[LRUHashtable] = None,
        # Use string annotation or TYPE_CHECKING to avoid NameError at import time
        dictionary: Optional['DictionaryStorage'] = None,
        checkpoint_dir: Optional[str] = None,
    ):
        # If a dictionary storage is supplied, use its backing memvid/cache
        if dictionary is not None:
            # Use dictionary internals directly
            self.memvid = dictionary.memvid
            self.hashtable = dictionary.cache
        else:
            # If neither memvid nor hashtable provided, default to a fused DictionaryStorage
            if memvid is None and hashtable is None:
                from ii_agent.storage.dictionary import DictionaryStorage as _Dictionary
                _dict = _Dictionary()
                self.memvid = _dict.memvid
                self.hashtable = _dict.cache
            else:
                self.memvid = memvid or MemvidStorage(
                video_dir=checkpoint_dir or str(Path.home() / ".ii_agent" / "checkpoints")
            )
                self.hashtable = hashtable or LRUHashtable(max_size=10000)

        self.checkpoint_metadata: Dict[str, Dict] = {}
        self._load_metadata()

    def _load_metadata(self):
        """Load checkpoint metadata index."""
        metadata_path = Path(self.memvid.video_dir) / "checkpoint_metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r') as f:
                    self.checkpoint_metadata = json.load(f)
            except Exception as e:
                logger.error(f"Error loading checkpoint metadata: {e}")
                self.checkpoint_metadata = {}

    def _save_metadata(self):
        """Save checkpoint metadata index."""
        metadata_path = Path(self.memvid.video_dir) / "checkpoint_metadata.json"
        try:
            with open(metadata_path, 'w') as f:
                json.dump(self.checkpoint_metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving checkpoint metadata: {e}")

    async def create_checkpoint(
        self,
        message_lists: List[List[GeneralContentBlock]],
        slab_id: Optional[str] = None,
        microkernel: Optional[Dict] = None,
    ) -> str:
        """
        Create checkpoint without evicting context.

        Args:
            message_lists: Conversation history to checkpoint
            slab_id: Optional checkpoint ID
            microkernel: Optional pre-checkpoint context summary (tasks, goals, current activity)

        Returns:
            Checkpoint ID
        """
        if slab_id is None:
            slab_id = f"slab_{int(datetime.now().timestamp())}"

        # Generate microkernel if not provided
        if microkernel is None:
            microkernel = self._generate_microkernel(message_lists)

        # Separate by retrieval intent
        payload = self._extract_payload(message_lists)
        backdrop = self._extract_backdrop(message_lists)

        # Inject microkernel into both payload and backdrop
        payload["microkernel"] = microkernel
        backdrop["microkernel"] = microkernel

        # Write to MemVid (QR-encoded MP4)
        payload_path = f"{slab_id}/payload"
        backdrop_path = f"{slab_id}/backdrop"

        self.memvid.write(
            content=self._to_binary(json.dumps(payload)),
            path=payload_path,
            content_type="application/json"
        )

        self.memvid.write(
            content=self._to_binary(json.dumps(backdrop)),
            path=backdrop_path,
            content_type="application/json"
        )

        # Index terms from payload
        self._index_checkpoint(slab_id, payload, backdrop)

        # Store metadata
        self.checkpoint_metadata[slab_id] = {
            "created_at": datetime.now().isoformat(),
            "payload_path": payload_path,
            "backdrop_path": backdrop_path,
            "keywords": payload.get("keywords", []) + backdrop.get("keywords", []),
            "file_refs": payload.get("file_refs", []),
            "topics": backdrop.get("topics", []),
        }
        self._save_metadata()

        logger.info(f"Created checkpoint {slab_id} (context NOT evicted)")
        return slab_id

    def _extract_payload(self, message_lists: List[List[GeneralContentBlock]]) -> Dict:
        """Extract operational state (todos, file_refs, tool_calls)."""
        payload = {
            "todos": [],
            "file_refs": [],
            "tool_calls": [],
            "tool_results": [],
            "code_changes": [],
            "test_results": [],
            "keywords": set(),
        }

        for message_list in message_lists:
            for message in message_list:
                if isinstance(message, ToolCall):
                    tool_data = {
                        "tool_name": message.tool_name,
                        "tool_input": message.tool_input,
                    }
                    payload["tool_calls"].append(tool_data)

                    # Extract todos
                    if message.tool_name == "TodoWrite":
                        if isinstance(message.tool_input, dict) and "todos" in message.tool_input:
                            payload["todos"] = message.tool_input["todos"]

                    # Extract file references
                    if message.tool_name in ["Read", "Write", "Edit"]:
                        if isinstance(message.tool_input, dict) and "file_path" in message.tool_input:
                            payload["file_refs"].append(message.tool_input["file_path"])
                            # Add filename as keyword
                            payload["keywords"].add(Path(message.tool_input["file_path"]).name)

                    # Extract code changes from Edit
                    if message.tool_name == "Edit":
                        if isinstance(message.tool_input, dict):
                            payload["code_changes"].append({
                                "file": message.tool_input.get("file_path"),
                                "old": message.tool_input.get("old_string", "")[:200],
                                "new": message.tool_input.get("new_string", "")[:200],
                            })

                elif isinstance(message, ToolFormattedResult):
                    payload["tool_results"].append({
                        "tool_name": message.tool_name,
                        "output": str(message.tool_output)[:500],
                    })

        payload["keywords"] = list(payload["keywords"])
        payload["file_refs"] = list(set(payload["file_refs"]))
        return payload

    def _extract_backdrop(self, message_lists: List[List[GeneralContentBlock]]) -> Dict:
        """Extract semantic context (thinking, explanations, intent)."""
        backdrop = {
            "user_intent": [],
            "thinking": [],
            "explanations": [],
            "topics": [],
            "keywords": set(),
        }

        for message_list in message_lists:
            for message in message_list:
                if isinstance(message, TextPrompt):
                    backdrop["user_intent"].append(message.text[:500])
                    # Extract keywords from user prompts
                    words = message.text.lower().split()
                    for word in words:
                        if len(word) > 4:
                            backdrop["keywords"].add(word)

                elif isinstance(message, ThinkingBlock):
                    backdrop["thinking"].append(message.thinking[:500])

                elif isinstance(message, TextResult):
                    backdrop["explanations"].append(message.text[:500])

        # Extract topics (simple keyword extraction)
        backdrop["topics"] = list(backdrop["keywords"])[:10]
        backdrop["keywords"] = list(backdrop["keywords"])

        return backdrop

    def _index_checkpoint(self, slab_id: str, payload: Dict, backdrop: Dict):
        """Index checkpoint terms in hashtable."""
        # Index file references
        for file_ref in payload.get("file_refs", []):
            existing = self.hashtable.get(file_ref)
            if existing:
                slab_ids = existing.content.decode('utf-8').split(',')
                if slab_id not in slab_ids:
                    slab_ids.append(slab_id)
                content = ','.join(slab_ids)
            else:
                content = slab_id

            from ii_agent.storage.hashtable import HashtableEntry
            self.hashtable.put(
                file_ref,
                HashtableEntry(content=content.encode('utf-8'))
            )

        # Index keywords
        all_keywords = set(payload.get("keywords", []) + backdrop.get("keywords", []))
        for keyword in all_keywords:
            existing = self.hashtable.get(keyword)
            if existing:
                slab_ids = existing.content.decode('utf-8').split(',')
                if slab_id not in slab_ids:
                    slab_ids.append(slab_id)
                content = ','.join(slab_ids)
            else:
                content = slab_id

            from ii_agent.storage.hashtable import HashtableEntry
            self.hashtable.put(
                keyword,
                HashtableEntry(content=content.encode('utf-8'))
            )

    def _generate_microkernel(self, message_lists: List[List[GeneralContentBlock]]) -> Dict:
        """
        Generate microkernel summary before checkpoint.

        Extracts the gist of:
        - Current tasks (from TodoWrite)
        - Goals (from user intent)
        - Current activity (recent operations)
        - Planned verbs (next actions)

        This helps model understand what breadcrumbs will be important.
        """
        microkernel = {
            "tasks": [],
            "goals": [],
            "current_activity": [],
            "planned_verbs": [],
            "important_breadcrumbs": [],
        }

        # Extract tasks from TodoWrite
        for message_list in reversed(message_lists[-10:]):  # Last 10 turns
            for message in message_list:
                if isinstance(message, ToolCall) and message.tool_name == "TodoWrite":
                    if isinstance(message.tool_input, dict) and "todos" in message.tool_input:
                        todos = message.tool_input["todos"]
                        for todo in todos:
                            if todo.get("status") != "completed":
                                microkernel["tasks"].append({
                                    "content": todo.get("content", ""),
                                    "status": todo.get("status", "pending"),
                                })

        # Extract goals from user prompts
        for message_list in message_lists[:5]:  # First 5 turns
            for message in message_list:
                if isinstance(message, TextPrompt):
                    microkernel["goals"].append(message.text[:200])

        # Extract current activity (recent tool calls)
        recent_tools = []
        for message_list in reversed(message_lists[-5:]):  # Last 5 turns
            for message in message_list:
                if isinstance(message, ToolCall):
                    recent_tools.append({
                        "tool": message.tool_name,
                        "context": str(message.tool_input)[:100],
                    })
        microkernel["current_activity"] = recent_tools[:5]

        # Extract planned verbs (imperative language from recent user prompts)
        for message_list in reversed(message_lists[-3:]):  # Last 3 turns
            for message in message_list:
                if isinstance(message, TextPrompt):
                    # Simple verb extraction (words followed by object)
                    words = message.text.lower().split()
                    verbs = [w for w in words if w in ["add", "create", "implement", "fix", "update", "refactor", "test", "debug", "analyze"]]
                    microkernel["planned_verbs"].extend(verbs[:3])

        # Mark important breadcrumbs (files, tests, key concepts)
        breadcrumbs = set()
        for message_list in message_lists[-10:]:  # Last 10 turns
            for message in message_list:
                if isinstance(message, ToolCall):
                    if message.tool_name in ["Read", "Write", "Edit"]:
                        if isinstance(message.tool_input, dict) and "file_path" in message.tool_input:
                            breadcrumbs.add(message.tool_input["file_path"])
        microkernel["important_breadcrumbs"] = list(breadcrumbs)[:10]

        return microkernel

    def _to_binary(self, content: str):
        """Convert string to BinaryIO."""
        import io
        return io.BytesIO(content.encode('utf-8'))

    def get_checkpoint(self, slab_id: str, slab_type: str = "payload") -> Optional[Dict]:
        """Retrieve checkpoint data."""
        if slab_id not in self.checkpoint_metadata:
            return None

        meta = self.checkpoint_metadata[slab_id]
        path = meta[f"{slab_type}_path"]

        try:
            content = self.memvid.read(path)
            data = json.loads(content.read().decode('utf-8'))
            return data
        except Exception as e:
            logger.error(f"Error reading checkpoint {slab_id}/{slab_type}: {e}")
            return None

    def query_checkpoints(self, query: str) -> List[str]:
        """Query checkpoints by term lookup."""
        # Extract terms from query
        terms = query.lower().split()

        slab_ids = set()
        for term in terms:
            entry = self.hashtable.get(term)
            if entry:
                ids = entry.content.decode('utf-8').split(',')
                slab_ids.update(ids)

        return list(slab_ids)
