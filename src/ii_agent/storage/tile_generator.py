"""Tile generation - create future checkpoint tiles from TODO structure."""

from typing import List, Dict, Optional
from datetime import datetime
import json

from ii_agent.llm.base import GeneralContentBlock, ToolCall
from ii_agent.storage.slab_checkpoint import SlabCheckpoint
from ii_agent.core.logger import logger


class TileGenerator:
    """
    Generate future checkpoint tiles based on TODO structure and semantic clusters.

    At N% context (default 33%), dump current work AND create compressed breadcrumb
    tiles for:
    1. Each pending TODO (structured work)
    2. Each semantic cluster (stochastic exploration)

    Each tile expands when activated (TODO starts, or cluster explored).
    Creates fan-out pattern for parallel work streams.
    """

    DEFAULT_DUMP_THRESHOLD = 0.33  # Default: dump at 33% context
    RETAIN_BREADCRUMBS = 0.05  # Retain 5% breadcrumbs after dump

    def __init__(
        self,
        checkpoint_system: SlabCheckpoint,
        dump_threshold: float = DEFAULT_DUMP_THRESHOLD,
    ):
        self.checkpoint_system = checkpoint_system
        self.dump_threshold = dump_threshold
        self.active_tiles: Dict[str, Dict] = {}  # tile_id -> tile metadata
        self.semantic_clusters: Dict[str, List[str]] = {}  # cluster_name -> breadcrumbs

    def should_dump_and_tile(self, context_tokens: int, context_window: int) -> bool:
        """Check if we should dump and generate tiles (at N% threshold)."""
        usage_ratio = context_tokens / context_window
        return usage_ratio >= self.dump_threshold

    async def dump_and_generate_tiles(
        self,
        message_lists: List[List[GeneralContentBlock]],
        context_window: int,
    ) -> Dict:
        """
        Dump current context and generate future tiles.

        Workflow:
        1. Dump current work to slab (checkpoint at 33%)
        2. Extract TODO list and task arrangement
        3. Generate compressed breadcrumb tile for each pending TODO
        4. Retain 5% breadcrumbs in active context
        5. Return tile metadata for activation

        Returns:
            {
                "current_slab_id": "slab_001",
                "tiles_generated": [
                    {"todo_id": "1", "tile_id": "tile_001", "content": "..."},
                    {"todo_id": "2", "tile_id": "tile_002", "content": "..."},
                ],
                "retained_breadcrumbs": ["auth.ts", "jwt.ts"],
            }
        """
        # 1. Create checkpoint for current work
        microkernel = self.checkpoint_system._generate_microkernel(message_lists)
        current_slab_id = await self.checkpoint_system.create_checkpoint(
            message_lists, microkernel=microkernel
        )

        logger.info(f"Dumped current work to {current_slab_id} at 33% context")

        # 2. Extract TODO list
        todos = self._extract_todos(message_lists)

        # 3a. Generate tiles for each pending TODO (structured work)
        tiles_generated = []
        for todo in todos:
            if todo.get("status") != "completed":
                tile = await self._generate_tile_for_todo(
                    todo, message_lists, microkernel, current_slab_id
                )
                tiles_generated.append(tile)
                self.active_tiles[tile["tile_id"]] = tile

        # 3b. Generate tiles for semantic clusters (stochastic exploration)
        semantic_tiles = await self._generate_semantic_cluster_tiles(
            message_lists, microkernel, current_slab_id
        )
        tiles_generated.extend(semantic_tiles)
        for tile in semantic_tiles:
            self.active_tiles[tile["tile_id"]] = tile

        # 4. Select breadcrumbs to retain (5% most important)
        retained_breadcrumbs = self._select_breadcrumbs_to_retain(
            microkernel, context_window
        )

        logger.info(
            f"Generated {len(tiles_generated)} future tiles, "
            f"retained {len(retained_breadcrumbs)} breadcrumbs"
        )

        return {
            "current_slab_id": current_slab_id,
            "tiles_generated": tiles_generated,
            "retained_breadcrumbs": retained_breadcrumbs,
        }

    async def _generate_tile_for_todo(
        self,
        todo: Dict,
        message_lists: List[List[GeneralContentBlock]],
        microkernel: Dict,
        parent_slab_id: str,
    ) -> Dict:
        """
        Generate compressed breadcrumb tile for a TODO.

        Tile contains:
        - TODO content and context
        - Relevant breadcrumbs (files, concepts)
        - Compressed context snapshot
        - Activation trigger (when TODO status changes)

        Tile will be expanded when TODO is activated.
        """
        todo_id = todo.get("id", "unknown")
        tile_id = f"tile_{todo_id}_{int(datetime.now().timestamp())}"

        # Extract relevant context for this TODO
        todo_content = todo.get("content", "")
        todo_context = self._extract_todo_context(todo_content, message_lists)

        # Identify relevant breadcrumbs
        relevant_breadcrumbs = self._identify_relevant_breadcrumbs(
            todo_content, microkernel.get("important_breadcrumbs", [])
        )

        # Optimize breadcrumb placement using ContextBandOptimizer
        try:
            from ii_agent.llm.context_band_optimizer import ContextBandOptimizer
            cbo = ContextBandOptimizer()
            # Create priority scores (heuristic: shorter filename = higher priority)
            priority_scores = [max(0.1, 1.0 - (len(b) / 200.0)) for b in relevant_breadcrumbs]
            placements = cbo.optimize_breadcrumb_placement(self.checkpoint_system.memvid.video_dir if hasattr(self.checkpoint_system, 'memvid') else 'default', relevant_breadcrumbs, priority_scores)
            # Mark which breadcrumbs are in golden bands
            breadcrumb_placement = {
                b: {'position': pos, 'in_golden_band': in_golden}
                for b, pos, in_golden in placements
            }
        except Exception:
            breadcrumb_placement = {b: {'position': 0.5, 'in_golden_band': False} for b in relevant_breadcrumbs}

        # Create compressed tile
        tile = {
            "tile_id": tile_id,
            "todo_id": todo_id,
            "todo_content": todo_content,
            "todo_status": todo.get("status", "pending"),
            "parent_slab_id": parent_slab_id,
            "compressed_context": {
                "breadcrumbs": relevant_breadcrumbs,
                "breadcrumb_placement": breadcrumb_placement,
                "related_activity": todo_context["activity"],
                "dependencies": todo_context["dependencies"],
                "estimated_scope": todo_context["scope"],
            },
            "activation_trigger": {
                "type": "todo_status_change",
                "todo_id": todo_id,
                "target_status": "in_progress",
            },
            "created_at": datetime.now().isoformat(),
        }

        # Store tile (compressed)
        tile_path = f"tiles/{tile_id}"
        self.checkpoint_system.memvid.write(
            content=self.checkpoint_system._to_binary(json.dumps(tile)),
            path=tile_path,
        )

        logger.info(f"Generated tile {tile_id} for TODO: {todo_content[:50]}")

        return tile

    def _extract_todos(self, message_lists: List[List[GeneralContentBlock]]) -> List[Dict]:
        """Extract TODO list from message history."""
        for message_list in reversed(message_lists):
            for message in message_list:
                if isinstance(message, ToolCall) and message.tool_name == "TodoWrite":
                    if isinstance(message.tool_input, dict) and "todos" in message.tool_input:
                        return message.tool_input["todos"]
        return []

    def _extract_todo_context(
        self, todo_content: str, message_lists: List[List[GeneralContentBlock]]
    ) -> Dict:
        """Extract context relevant to this TODO."""
        context = {
            "activity": [],
            "dependencies": [],
            "scope": "small",  # small, medium, large
        }

        # Search for related activity (tool calls mentioning TODO keywords)
        keywords = set(todo_content.lower().split())
        for message_list in reversed(message_lists[-10:]):  # Last 10 turns
            for message in message_list:
                if isinstance(message, ToolCall):
                    tool_context = str(message.tool_input).lower()
                    if any(kw in tool_context for kw in keywords):
                        context["activity"].append({
                            "tool": message.tool_name,
                            "context": str(message.tool_input)[:100],
                        })

        # Estimate scope based on complexity
        if len(context["activity"]) > 5:
            context["scope"] = "large"
        elif len(context["activity"]) > 2:
            context["scope"] = "medium"

        return context

    def _identify_relevant_breadcrumbs(
        self, todo_content: str, all_breadcrumbs: List[str]
    ) -> List[str]:
        """Identify breadcrumbs relevant to this TODO."""
        keywords = set(todo_content.lower().split())
        relevant = []

        for breadcrumb in all_breadcrumbs:
            breadcrumb_lower = breadcrumb.lower()
            # Check if any TODO keyword appears in breadcrumb path
            if any(kw in breadcrumb_lower for kw in keywords):
                relevant.append(breadcrumb)

        return relevant[:5]  # Top 5 most relevant

    def _select_breadcrumbs_to_retain(
        self, microkernel: Dict, context_window: int
    ) -> List[str]:
        """Select 5% most important breadcrumbs to retain in active context."""
        breadcrumbs = microkernel.get("important_breadcrumbs", [])

        # Calculate how many to retain (5% of context window, in terms of items)
        # Assume average breadcrumb is ~50 tokens
        retain_count = max(3, min(10, int(context_window * 0.05 / 50)))

        # Prioritize:
        # 1. Files from current activity
        # 2. Files from recent edits
        # 3. Files mentioned in pending tasks

        current_activity_files = set()
        for activity in microkernel.get("current_activity", [])[:3]:
            context = activity.get("context", "")
            # Extract file paths from context (simple heuristic)
            for breadcrumb in breadcrumbs:
                if breadcrumb in context:
                    current_activity_files.add(breadcrumb)

        # Start with current activity files
        retained = list(current_activity_files)[:retain_count]

        # Fill remaining slots with most recent breadcrumbs
        for breadcrumb in breadcrumbs:
            if breadcrumb not in retained and len(retained) < retain_count:
                retained.append(breadcrumb)

        return retained

    async def activate_tile(self, todo_id: str) -> Optional[Dict]:
        """
        Activate tile when TODO status changes to in_progress.

        Expands compressed tile into full context for that TODO.

        Returns:
            Expanded context for the TODO, or None if tile not found
        """
        if todo_id not in self.active_tiles:
            logger.warning(f"No active tile found for TODO {todo_id}")
            return None

        tile_metadata = self.active_tiles[todo_id]
        tile_id = tile_metadata["tile_id"]

        # Read compressed tile
        tile_path = f"tiles/{tile_id}"
        tile_data_binary = self.checkpoint_system.memvid.read(tile_path)
        tile_data = json.loads(tile_data_binary.read().decode('utf-8'))

        # Expand tile: retrieve full context from parent slab
        parent_slab_id = tile_data["parent_slab_id"]
        parent_payload = self.checkpoint_system.get_checkpoint(
            parent_slab_id, slab_type="payload"
        )
        parent_backdrop = self.checkpoint_system.get_checkpoint(
            parent_slab_id, slab_type="backdrop"
        )

        # Filter to relevant context
        expanded_context = {
            "tile_id": tile_id,
            "todo_content": tile_data["todo_content"],
            "breadcrumbs": tile_data["compressed_context"]["breadcrumbs"],
            "relevant_files": self._extract_relevant_files(
                tile_data["compressed_context"]["breadcrumbs"], parent_payload
            ),
            "relevant_activity": tile_data["compressed_context"]["related_activity"],
            "parent_context": {
                "tasks": parent_payload.get("microkernel", {}).get("tasks", []),
                "goals": parent_backdrop.get("microkernel", {}).get("goals", []),
            },
        }

        logger.info(f"Activated tile {tile_id} for TODO: {tile_data['todo_content'][:50]}")

        return expanded_context

    def _extract_relevant_files(
        self, breadcrumbs: List[str], payload: Dict
    ) -> List[Dict]:
        """Extract file content and changes for relevant breadcrumbs."""
        relevant_files = []

        file_refs = payload.get("file_refs", [])
        code_changes = payload.get("code_changes", [])

        for breadcrumb in breadcrumbs:
            if breadcrumb in file_refs:
                # Find associated code changes
                changes_for_file = [
                    change for change in code_changes
                    if change.get("file") == breadcrumb
                ]

                relevant_files.append({
                    "file": breadcrumb,
                    "changes": changes_for_file,
                })

        return relevant_files

    async def _generate_semantic_cluster_tiles(
        self,
        message_lists: List[List[GeneralContentBlock]],
        microkernel: Dict,
        parent_slab_id: str,
    ) -> List[Dict]:
        """
        Generate tiles for semantic clusters (stochastic exploration).

        Analyzes conversation to identify semantic clusters (topics, concepts)
        that could be explored independently. Creates compressed tile for each.

        Enables forking off exploration paths without structured TODOs.
        """
        # Extract semantic clusters from thinking and explanations
        clusters = self._identify_semantic_clusters(message_lists, microkernel)

        semantic_tiles = []
        for cluster_name, cluster_data in clusters.items():
            tile_id = f"tile_semantic_{cluster_name}_{int(datetime.now().timestamp())}"

            tile = {
                "tile_id": tile_id,
                "tile_type": "semantic_cluster",
                "cluster_name": cluster_name,
                "parent_slab_id": parent_slab_id,
                "compressed_context": {
                    "breadcrumbs": cluster_data["breadcrumbs"],
                    "concepts": cluster_data["concepts"],
                    "exploration_hints": cluster_data["hints"],
                },
                "activation_trigger": {
                    "type": "semantic_query",
                    "cluster_name": cluster_name,
                    "keywords": cluster_data["keywords"],
                },
                "created_at": datetime.now().isoformat(),
            }

            # Store tile
            tile_path = f"tiles/{tile_id}"
            self.checkpoint_system.memvid.write(
                content=self.checkpoint_system._to_binary(json.dumps(tile)),
                path=tile_path,
            )

            semantic_tiles.append(tile)
            self.semantic_clusters[cluster_name] = cluster_data["breadcrumbs"]

            logger.info(f"Generated semantic cluster tile: {cluster_name}")

        return semantic_tiles

    def _identify_semantic_clusters(
        self, message_lists: List[List[GeneralContentBlock]], microkernel: Dict
    ) -> Dict[str, Dict]:
        """
        Identify semantic clusters for stochastic exploration.

        Clusters are identified by:
        - Repeated concepts in thinking blocks
        - File/concept co-occurrence
        - Exploration branches in conversation
        """
        from ii_agent.llm.base import ThinkingBlock, TextResult

        clusters = {}

        # Extract concepts from thinking blocks
        concepts_mentioned = {}
        for message_list in message_lists[-20:]:  # Last 20 turns
            for message in message_list:
                if isinstance(message, ThinkingBlock):
                    # Simple concept extraction (words appearing multiple times)
                    words = message.thinking.lower().split()
                    for word in words:
                        if len(word) > 5:  # Significant words
                            concepts_mentioned[word] = concepts_mentioned.get(word, 0) + 1

        # Find top concepts (mentioned 3+ times)
        top_concepts = {k: v for k, v in concepts_mentioned.items() if v >= 3}

        # Create cluster for each top concept
        for concept, count in list(top_concepts.items())[:5]:  # Max 5 clusters
            # Find related breadcrumbs
            related_breadcrumbs = []
            for breadcrumb in microkernel.get("important_breadcrumbs", []):
                if concept in breadcrumb.lower():
                    related_breadcrumbs.append(breadcrumb)

            if related_breadcrumbs:
                clusters[concept] = {
                    "breadcrumbs": related_breadcrumbs,
                    "concepts": [concept],
                    "hints": [f"Explore {concept} in depth"],
                    "keywords": [concept],
                }

        # Identify file co-occurrence clusters
        file_groups = self._find_file_cooccurrence_groups(microkernel)
        for i, group in enumerate(file_groups[:3]):  # Max 3 file groups
            cluster_name = f"file_group_{i+1}"
            clusters[cluster_name] = {
                "breadcrumbs": group["files"],
                "concepts": [f"Related files: {', '.join(group['files'][:2])}"],
                "hints": [f"Explore related files: {', '.join(group['files'])}"],
                "keywords": group["files"],
            }

        return clusters

    def _find_file_cooccurrence_groups(self, microkernel: Dict) -> List[Dict]:
        """Find files that appear together in recent activity."""
        activity = microkernel.get("current_activity", [])

        # Build co-occurrence matrix
        file_pairs = {}
        for act in activity:
            context = act.get("context", "")
            files_in_context = [
                b for b in microkernel.get("important_breadcrumbs", [])
                if b in context
            ]

            # Record pairs
            for i, f1 in enumerate(files_in_context):
                for f2 in files_in_context[i+1:]:
                    pair = tuple(sorted([f1, f2]))
                    file_pairs[pair] = file_pairs.get(pair, 0) + 1

        # Find groups (files that co-occur frequently)
        groups = []
        for (f1, f2), count in file_pairs.items():
            if count >= 2:
                groups.append({"files": [f1, f2], "count": count})

        return groups

    def fan_out_tiles(self) -> Dict:
        """
        Fan out active tiles for parallel work streams.

        Returns metadata for each active tile, allowing:
        - Parallel TODO execution (structured work)
        - Parallel semantic exploration (stochastic)
        """
        fan_out = {
            "total_tiles": len(self.active_tiles),
            "structured_tiles": [],  # TODO-based
            "exploration_tiles": [],  # Semantic clusters
        }

        for tile_id, tile in self.active_tiles.items():
            tile_metadata = {
                "tile_id": tile["tile_id"],
                "breadcrumbs": tile["compressed_context"]["breadcrumbs"],
            }

            if tile.get("tile_type") == "semantic_cluster":
                tile_metadata["cluster_name"] = tile["cluster_name"]
                tile_metadata["concepts"] = tile["compressed_context"]["concepts"]
                fan_out["exploration_tiles"].append(tile_metadata)
            else:
                tile_metadata["todo_content"] = tile["todo_content"]
                tile_metadata["scope"] = tile["compressed_context"]["estimated_scope"]
                fan_out["structured_tiles"].append(tile_metadata)

        logger.info(
            f"Fan-out: {len(fan_out['structured_tiles'])} structured, "
            f"{len(fan_out['exploration_tiles'])} exploration tiles"
        )

        return fan_out
