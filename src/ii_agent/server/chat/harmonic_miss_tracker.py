"""Harmonic miss tracking - monitor edit slips and errors per model over time."""

from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path

from ii_agent.core.logger import logger


class HarmonicMissTracker:
    """
    Track 'harmonic miss' events - errors caused by context pressure.

    Different models create more errors at different context thresholds.
    This tracker monitors edit slips, hallucinations, and inconsistencies
    to tune model-specific checkpoint thresholds over time.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path or Path.home() / ".ii_agent" / "harmonic_miss_log.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, List[Dict]] = self._load()

    def _load(self) -> Dict[str, List[Dict]]:
        """Load historical data from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading harmonic miss log: {e}")
        return {}

    def _save(self):
        """Persist data to disk."""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving harmonic miss log: {e}")

    def track(
        self,
        model_id: str,
        error_type: str,
        context_tokens: int,
        context_window: int,
        metadata: Optional[Dict] = None,
    ):
        """
        Track a harmonic miss event.

        Args:
            model_id: Model identifier
            error_type: Type of error (edit_slip, hallucination, inconsistency, etc.)
            context_tokens: Token count when error occurred
            context_window: Model's total context window size
            metadata: Additional context (file path, operation, etc.)
        """
        if model_id not in self._data:
            self._data[model_id] = []

        event = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "context_tokens": context_tokens,
            "context_window": context_window,
            "pressure_ratio": context_tokens / context_window,
            "metadata": metadata or {},
        }

        self._data[model_id].append(event)

        # Keep last 1000 events per model
        if len(self._data[model_id]) > 1000:
            self._data[model_id] = self._data[model_id][-1000:]

        self._save()

        logger.warning(
            f"Harmonic miss: {model_id} - {error_type} at {context_tokens} tokens "
            f"({event['pressure_ratio']:.1%} pressure)"
        )

    def get_stats(self, model_id: str) -> Dict:
        """Get statistics for a model."""
        events = self._data.get(model_id, [])
        if not events:
            return {
                "model_id": model_id,
                "total_events": 0,
                "error_types": {},
                "avg_pressure": 0.0,
            }

        # Count error types
        error_types = {}
        for event in events:
            error_type = event["error_type"]
            error_types[error_type] = error_types.get(error_type, 0) + 1

        # Calculate average pressure
        avg_pressure = sum(e["pressure_ratio"] for e in events) / len(events)

        # Find pressure ranges where errors cluster
        pressure_buckets = {
            "0-25%": 0,
            "25-50%": 0,
            "50-75%": 0,
            "75-90%": 0,
            "90-100%": 0,
        }

        for event in events:
            pressure = event["pressure_ratio"]
            if pressure < 0.25:
                pressure_buckets["0-25%"] += 1
            elif pressure < 0.50:
                pressure_buckets["25-50%"] += 1
            elif pressure < 0.75:
                pressure_buckets["50-75%"] += 1
            elif pressure < 0.90:
                pressure_buckets["75-90%"] += 1
            else:
                pressure_buckets["90-100%"] += 1

        return {
            "model_id": model_id,
            "total_events": len(events),
            "error_types": error_types,
            "avg_pressure": avg_pressure,
            "pressure_distribution": pressure_buckets,
            "recent_events": events[-10:],
        }

    def recommend_threshold(self, model_id: str) -> Optional[float]:
        """
        Recommend checkpoint threshold based on harmonic miss patterns.

        Analyzes where errors cluster and recommends threshold to checkpoint
        before entering high-error pressure zones.

        Returns:
            Recommended threshold as percentage (0.0 to 1.0), or None if insufficient data
        """
        stats = self.get_stats(model_id)

        if stats["total_events"] < 10:
            return None  # Insufficient data

        # Find pressure bucket with highest error rate
        buckets = stats["pressure_distribution"]
        max_errors = max(buckets.values())

        # If most errors in 90-100%, recommend 75%
        if buckets["90-100%"] == max_errors:
            return 0.75

        # If most errors in 75-90%, recommend 60%
        if buckets["75-90%"] == max_errors:
            return 0.60

        # If most errors in 50-75%, recommend 40%
        if buckets["50-75%"] == max_errors:
            return 0.40

        # Otherwise use average pressure - 10% as safety margin
        return max(0.15, stats["avg_pressure"] - 0.10)

    def get_all_models(self) -> List[str]:
        """Get list of all tracked models."""
        return list(self._data.keys())

    def export_report(self) -> str:
        """Export human-readable report."""
        lines = ["# Harmonic Miss Report\n"]

        for model_id in self.get_all_models():
            stats = self.get_stats(model_id)
            recommended = self.recommend_threshold(model_id)

            lines.append(f"\n## {model_id}")
            lines.append(f"Total events: {stats['total_events']}")
            lines.append(f"Avg pressure: {stats['avg_pressure']:.1%}")
            lines.append(f"\nError types:")
            for error_type, count in stats['error_types'].items():
                lines.append(f"  - {error_type}: {count}")
            lines.append(f"\nPressure distribution:")
            for bucket, count in stats['pressure_distribution'].items():
                lines.append(f"  - {bucket}: {count}")

            if recommended:
                lines.append(f"\nRecommended checkpoint threshold: {recommended:.0%}")

        return "\n".join(lines)
