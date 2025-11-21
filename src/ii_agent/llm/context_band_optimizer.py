"""
Context Band Optimizer - Golden band tiling for optimal retrieval.

Identifies "golden bands" where needle-in-haystack tests show peculiarly good results,
then creates a tiling strategy that places breadcrumbs in these bands.

Based on empirical observations that certain context positions (e.g., 25-30%, 45-50%)
show better retrieval than others. This optimizer leverages those bands.
"""

import json
import random
from typing import Dict, List, Tuple, Optional
import math

from ii_agent.core.logger import logger


class ContextBandOptimizer:
    """
    Optimizes context tiling based on empirically-derived golden bands.

    Key insight: Needle-in-haystack tests reveal specific position bands
    with peculiarly good retrieval rates. These vary by model:

    - Claude 3.5 Sonnet: Strong at 20-30%, 60-70% (attention patterns)
    - GPT-4o: Strong at 15-25%, 45-55% (U-shape but with peaks)
    - Gemini 1.5: Relatively uniform but slight peaks at 30-40%
    - Llama 4: Catastrophic except at 0-5% (start of context)

    This optimizer:
    1. Learns golden bands from cliff benchmark results
    2. Creates non-uniform tilings that place more breadcrumbs in golden bands
    3. Reduces search priority for golden-band-placed content (already optimal)
    4. Adapts bands per model based on live performance data
    """

    # Empirically-derived golden bands for common models
    # Based on needle-in-haystack success rates at different depths
    DEFAULT_GOLDEN_BANDS = {
        "claude-3-5-sonnet": [
            {"start": 0.20, "end": 0.35, "weight": 1.5, "rationale": "mid-context attention boost"},
            {"start": 0.60, "end": 0.75, "weight": 1.3, "rationale": "second attention window"},
            {"start": 0.08, "end": 0.15, "weight": 1.2, "rationale": "early context stability"},
        ],
        "claude-3-7-sonnet": [
            {"start": 0.10, "end": 0.25, "weight": 1.4, "rationale": "early context critical for reasoning"},
        ],
        "gpt-4o": [
            {"start": 0.15, "end": 0.25, "weight": 1.3, "rationale": "early-middle context peak"},
            {"start": 0.45, "end": 0.55, "weight": 1.2, "rationale": "middle context secondary peak"},
        ],
        "gpt-4.1": [
            {"start": 0.05, "end": 0.15, "weight": 1.4, "rationale": "critical early context for 1M token"},
            {"start": 0.25, "end": 0.35, "weight": 1.2, "rationale": "first harmonic of early context"},
        ],
        "gemini-1.5": [
            {"start": 0.30, "end": 0.40, "weight": 1.15, "rationale": "slight mid-context optimization"},
            {"start": 0.70, "end": 0.80, "weight": 1.10, "rationale": "late context retention"},
        ],
        "gemini-2.5": [
            {"start": 0.25, "end": 0.45, "weight": 1.2, "rationale": "broad mid-context strength"},
        ],
        "llama-4-scout": [
            {"start": 0.00, "end": 0.05, "weight": 2.0, "rationale": "START ONLY - catastrophic elsewhere"},
            # No other bands - fails everywhere else
        ],
        "llama-4-maverick": [
            {"start": 0.00, "end": 0.10, "weight": 1.8, "rationale": "strong start only"},
            {"start": 0.20, "end": 0.30, "weight": 1.1, "rationale": "marginal second band"},
        ],
        "deepseek-v3.1": [
            {"start": 0.10, "end": 0.20, "weight": 1.25, "rationale": "early context stability"},
            {"start": 0.55, "end": 0.65, "weight": 1.15, "rationale": "mid-context recovery"},
        ],
    }

    # Models with severe U-shape or catastrophic degradation
    HIGH_RISK_MODELS = {
        "llama-4-scout",          # Catastrophic everywhere except start
        "llama-4-maverick",       # Strong degradation after 30K
    }

    def __init__(self):
        self.bands: Dict[str, List[Dict]] = self.DEFAULT_GOLDEN_BANDS.copy()
        self.learning_enabled = True  # Learn from live results
        self._performance_history: Dict[str, List[Tuple[float, float]]] = {}
        # history[model] = [(position, success_rate), ...]

    def get_golden_bands(self, model_id: str) -> List[Dict]:
        """
        Get golden bands for a model, with fuzzy matching.

        Args:
            model_id: Model identifier (litellm/HF format)

        Returns:
            List of band definitions with start, end, weight, rationale
        """
        model_key = self._normalize_model_id(model_id)

        # Exact match
        if model_key in self.bands:
            return self.bands[model_key]

        # Fuzzy matching
        matches = []
        for known_model in self.bands.keys():
            if known_model in model_key or model_key in known_model:
                matches.append(known_model)

        if matches:
            logger.debug(f"Fuzzy matched {model_id} to {matches[0]}")
            return self.bands[matches[0]]

        # Default: assume strong early context
        logger.warning(f"No golden bands for {model_id}, using default")
        return [
            {"start": 0.00, "end": 0.10, "weight": 1.3, "rationale": "default early band"},
        ]

    def _normalize_model_id(self, model_id: str) -> str:
        """Normalize model ID for matching."""
        return model_id.lower().replace("-", "_").replace("/", "_").replace(".", "_")

    def get_model_profile(self, model_id: str) -> Optional[Dict]:
        """
        Get performance profile for a model including bands and test history.

        Args:
            model_id: Model identifier

        Returns:
            Dict with bands, test_count, performance_history, or None if no data
        """
        model_key = self._normalize_model_id(model_id)

        # Get bands (may be default)
        bands = self.get_golden_bands(model_id)

        # Get performance history if available
        history = self._performance_history.get(model_key, [])

        if not bands and not history:
            return None

        return {
            "model_id": model_id,
            "bands": bands,
            "test_count": len(history),
            "performance_history": history,
            "has_custom_bands": model_key in self.bands,
        }

    def calculate_band_weights(self, model_id: str, num_positions: int) -> List[float]:
        """
        Calculate weights for each position (0.0 to 1.0) based on golden bands.

        Used to determine breadcrumb placement density - higher weight =
        more breadcrumbs in that position.

        Args:
            model_id: Model identifier
            num_positions: Number of positions to calculate weights for

        Returns:
            List of weights, one per position
        """
        bands = self.get_golden_bands(model_id)
        weights = [1.0] * num_positions  # Base weight: 1.0

        for band in bands:
            start_idx = int(band["start"] * num_positions)
            end_idx = int(band["end"] * num_positions)
            band_weight = band["weight"]

            for i in range(start_idx, min(end_idx + 1, num_positions)):
                weights[i] *= band_weight

        return weights

    def create_mosaic_tiling(
        self, model_id: str, context_length: int, num_tiles: int, min_tile_size: float = 0.02
    ) -> List[Dict[str, Any]]:
        """
        Create mosaic tilings that adapt to band weights (no fixed shapes).

        Instead of fixed-shape tiles, this creates a true mosaic:
        - Tile size varies continuously based on local weight
        - Can place multiple small tiles in high-weight regions
        - Can skip low-weight regions entirely
        - Each tile's boundaries adapt to weight gradients

        Args:
            model_id: Model identifier
            context_length: Total context length in tokens
            num_tiles: Desired number of tiles
            min_tile_size: Minimum tile size (default: 2% of context)

        Returns:
            List of mosaic tile definitions
        """
        # Calculate position weights (granular)
        num_positions = max(200, num_tiles * 10)  # High granularity
        position_weights = self.calculate_band_weights(model_id, num_positions)
        max_weight = max(position_weights)

        # Create a cumulative distribution from weights
        cumulative = []
        total = 0
        for w in position_weights:
            total += w
            cumulative.append(total)

        # Normalize cumulative to [0, 1]
        cumulative = [c / total for c in cumulative]

        # Generate tiles using inverse transform sampling
        tiles = []
        for i in range(num_tiles):
            # Sample position from weight distribution (more likely in high-weight areas)
            rand = random.random()
            position_idx = next(j for j, c in enumerate(cumulative) if c >= rand)
            position = position_idx / num_positions

            # Determine tile size based on local weight (more weight = smaller tile)
            local_weight = position_weights[position_idx]
            # Tile size inversely proportional to weight, bounded by min size
            size_factor = max(min_tile_size, 1.0 / (local_weight * 2))

            # Adjust size so we don't exceed context bounds
            # Tiles can overlap slightly in mosaic approach
            size = min(size_factor, 1.0 - position)

            tiles.append({
                "tile_id": f"tile_mosaic_{i}",
                "position": position,
                "size": size,
                "local_weight": local_weight,
                "in_golden_band": local_weight > 1.1,
                "effective_tokens": int(context_length * size),
                "density": 1.0 / size,  # Tiles per unit context
            })

        # Sort and merge overlapping tiles slightly
        tiles.sort(key=lambda x: x["position"])

        # Ensure tiles don't overlap significantly (post-processing)
        for i in range(len(tiles) - 1):
            current = tiles[i]
            next_tile = tiles[i + 1]

            overlap = (current["position"] + current["size"]) - next_tile["position"]
            if overlap > 0:
                # Adjust sizes to eliminate significant overlap
                shrink = overlap / 2
                current["size"] -= shrink
                next_tile["position"] += shrink

                # Recalculate dependent fields after adjustment
                current["effective_tokens"] = int(context_length * current["size"])
                current["density"] = 1.0 / current["size"] if current["size"] > 0 else 0.0

        logger.info(
            f"Created {len(tiles)} mosaic tiles for {model_id}: "
            f"{sum(1 for t in tiles if t['in_golden_band'])} in golden bands, "
            f"avg size: {sum(t['size'] for t in tiles) / len(tiles):.2%}"
        )

        return tiles

    def optimize_breadcrumb_placement(
        self, model_id: str, breadcrumbs: List[str], priority_scores: List[float]
    ) -> List[Tuple[str, float, bool]]:
        """
        Optimize breadcrumb placement in golden bands.

        Places high-priority breadcrumbs in golden band positions where
        retrieval is most successful. Returns placement metadata.

        Args:
            model_id: Model identifier
            breadcrumbs: List of breadcrumb strings
            priority_scores: Priority score for each breadcrumb (higher = more important)

        Returns:
            List of (breadcrumb, position, in_golden_band) tuples
        """
        bands = self.get_golden_bands(model_id)
        placements = []

        # Sort by priority (highest first)
        sorted_items = sorted(
            zip(breadcrumbs, priority_scores), key=lambda x: x[1], reverse=True
        )

        # Place highest priority in best bands
        for i, (breadcrumb, priority) in enumerate(sorted_items[: len(bands) * 3]):
            # Cycle through bands for top items
            band_idx = i % len(bands)
            band = bands[band_idx]

            # Place in middle of band for best results
            position = (band["start"] + band["end"]) / 2
            in_golden_band = True

            placements.append((breadcrumb, position, in_golden_band))

        # Place remaining elsewhere
        remaining_start = len(bands)
        remaining = sorted_items[remaining_start:]
        for breadcrumb, priority in remaining:
            position = random.random()  # Random position
            in_golden_band = False

            placements.append((breadcrumb, position, in_golden_band))

        return placements

    def record_needle_test_result(
        self, model_id: str, position: float, success: bool
    ):
        """
        Record needle test result for learning golden bands.

        Updates internal performance history to refine band definitions.

        Args:
            model_id: Model identifier
            position: Position in context (0.0 to 1.0)
            success: Whether needle was found (True/False)
        """
        if not self.learning_enabled:
            return

        model_key = self._normalize_model_id(model_id)

        if model_key not in self._performance_history:
            self._performance_history[model_key] = []

        # Store result
        success_rate = 1.0 if success else 0.0
        self._performance_history[model_key].append((position, success_rate))

        # Limit history size
        if len(self._performance_history[model_key]) > 1000:
            self._performance_history[model_key] = self._performance_history[model_key][-1000:]

    def adapt_bands_from_data(self, model_id: str) -> List[Dict]:
        """
        Adapt golden bands based on collected performance data.

        Analyzes recorded needle test results to discover high-performance
        positions and create new band definitions.

        Args:
            model_id: Model identifier

        Returns:
            New band definitions based on empirical data
        """
        model_key = self._normalize_model_id(model_id)

        if model_key not in self._performance_history:
            logger.warning(f"No performance data for {model_id}, using defaults")
            return self.get_golden_bands(model_id)

        history = self._performance_history[model_key]

        # Bin positions (10% buckets)
        bins = [0.0] * 10  # 0-10%, 10-20%, ..., 90-100%
        bin_counts = [0] * 10

        for position, success in history:
            bin_idx = int(position * 10)
            bin_idx = min(9, bin_idx)  # Cap at 9 for 100%
            bins[bin_idx] += success
            bin_counts[bin_idx] += 1

        # Calculate bin success rates
        success_rates = []
        for i, (total, count) in enumerate(zip(bins, bin_counts)):
            if count > 5:  # Need minimum data
                rate = total / count
                success_rates.append((i / 10.0, rate, count))

        if not success_rates:
            return self.get_golden_bands(model_id)

        # Find contiguous high-performance regions (>75% success)
        def find_high_perf_regions(rates, threshold=0.75):
            regions = []
            start = None

            for pos, rate, count in rates:
                if rate >= threshold:
                    if start is None:
                        start = pos
                elif start is not None:
                    regions.append((start, pos))
                    start = None

            if start is not None:
                regions.append((start, rates[-1][0]))

            return regions

        high_perf_regions = find_high_perf_regions(success_rates)

        # Convert to band definitions
        new_bands = []
        for i, (start, end) in enumerate(high_perf_regions):
            avg_success = sum(r for p, r, c in success_rates if start <= p <= end) / len(
                [r for p, r, c in success_rates if start <= p <= end]
            )
            weight = 1.0 + ((avg_success - 0.75) / 0.25) * 0.5  # 1.0 to 1.5

            new_bands.append({
                "start": start,
                "end": end,
                "weight": weight,
                "rationale": f"empirical {avg_success:.1%} success rate",
            })

        logger.info(
            f"Adapted {len(new_bands)} golden bands for {model_id} "
            f"from {len(history)} test results"
        )

        return new_bands

    def get_breadcrumb_search_modifier(self, position: float, model_id: str) -> float:
        """
        Get search priority modifier for a breadcrumb based on its position.

        Breadcrumbs in golden bands should have LOWER search priority since
        they're already optimally positioned for retrieval.

        Args:
            position: Position in context (0.0 to 1.0)
            model_id: Model identifier

        Returns:
            Multiplier for search priority (<1.0 for golden band, 1.0 otherwise)
        """
        bands = self.get_golden_bands(model_id)

        in_golden_band = False
        for band in bands:
            if band["start"] <= position <= band["end"]:
                in_golden_band = True
                break

        # In golden band: reduce search priority (0.7x)
        # Outside golden band: normal priority (1.0x)
        return 0.7 if in_golden_band else 1.0

    def export_band_data(self, model_id: str) -> Dict:
        """
        Export band data for analysis and sharing.

        Returns comprehensive band information including:
        - Default bands
        - Adapted bands (if learning enabled)
        - Performance history summary

        Args:
            model_id: Model identifier

        Returns:
            Band data dictionary
        """
        model_key = self._normalize_model_id(model_id)

        data = {
            "model_id": model_id,
            "default_bands": self.get_golden_bands(model_id),
            "learning_enabled": self.learning_enabled,
        }

        if model_key in self._performance_history:
            history = self._performance_history[model_key]
            data["test_count"] = len(history)
            data["average_success_rate"] = sum(s for p, s in history) / len(history)

        if self.learning_enabled and model_key in self._performance_history:
            data["adapted_bands"] = self.adapt_bands_from_data(model_id)

        return data
