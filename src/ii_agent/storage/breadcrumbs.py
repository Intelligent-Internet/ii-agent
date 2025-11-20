"""Breadcrumb navigation for slab checkpoints."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Tuple, Dict, Any, Optional


class BreadcrumbRelationType(Enum):
    """Semantic relationships between slabs."""

    CONTINUATION = "→"
    INTERLEAVED = "⇄"
    FIXES = "⟳"
    EXTENDS = "↗"
    REFACTORS = "↻"
    REVERTS = "↶"
    REFERENCES = "⇢"
    MERGES = "⊕"
    BRANCHES = "⑂"
    DEPENDS = "⊳"
    CLARIFIES = "◉"
    INVALIDATES = "⊗"
    VALIDATES = "✓"


@dataclass
class Breadcrumb:
    """Single node in breadcrumb trail."""

    slab_id: str
    slab_type: str  # "payload" or "backdrop"
    primary_topic: str
    keywords: List[str]
    file_refs: List[str]
    created_at: datetime
    turn_range: Tuple[int, int]
    inbound_relations: List[Tuple[str, BreadcrumbRelationType]]
    outbound_relations: List[Tuple[str, BreadcrumbRelationType]]
    relevance_score: float
    access_count: int = 0

    def __str__(self):
        return f"[{self.slab_id}] {self.primary_topic}"


@dataclass
class BreadcrumbTrail:
    """Ordered sequence of breadcrumbs showing semantic path."""

    query: str
    breadcrumbs: List[Breadcrumb]
    relations: List[Tuple[int, int, BreadcrumbRelationType]]

    def render_text(self) -> str:
        """Render trail as text with categorical arrows."""
        if not self.breadcrumbs:
            return f"Query: {self.query}\n(No results)"

        parts = [f"Query: {self.query}\n"]

        for i, crumb in enumerate(self.breadcrumbs):
            parts.append(f"\n[{crumb.slab_id}] {crumb.primary_topic}")
            parts.append(f"\n  Keywords: {', '.join(crumb.keywords[:3])}")
            parts.append(f"\n  Files: {', '.join(crumb.file_refs[:2])}")

            if i < len(self.breadcrumbs) - 1:
                rel = self._get_relation(i, i + 1)
                arrow = rel.value if rel else "↓"
                parts.append(f"\n    {arrow}")

        return "".join(parts)

    def _get_relation(self, from_idx: int, to_idx: int) -> Optional[BreadcrumbRelationType]:
        """Get relation between two breadcrumbs."""
        for f, t, rel_type in self.relations:
            if f == from_idx and t == to_idx:
                return rel_type
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for tool output."""
        return {
            "query": self.query,
            "breadcrumbs": [
                {
                    "slab_id": c.slab_id,
                    "topic": c.primary_topic,
                    "keywords": c.keywords,
                    "files": c.file_refs,
                    "relevance": c.relevance_score,
                }
                for c in self.breadcrumbs
            ],
            "trail": self.render_text(),
        }
