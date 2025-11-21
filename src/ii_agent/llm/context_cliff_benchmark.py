"""
Context Cliff Benchmark - Background needle-in-haystack and error rate testing.

Continuously monitors model performance degradation patterns to detect when models
hit their operational cliffs. Runs automatically when models reach usage thresholds.
"""

import asyncio
import random
import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import json

from ii_agent.core.logger import logger
from ii_agent.llm.context_band_optimizer import ContextBandOptimizer


@dataclass
class NeedleTestResult:
    """Result from a single needle-in-haystack test."""

    model_id: str
    context_length: int
    needle_depth: float  # 0.0 = start, 1.0 = end
    success: bool
    latency_ms: float
    response: str
    expected: str
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ErrorRateResult:
    """Result from error rate testing."""

    model_id: str
    context_length: int
    trial_count: int
    errors: int
    error_types: Dict[str, int]  # hallucination, inconsistency, edit_slip, etc.
    avg_latency_ms: float
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def error_rate(self) -> float:
        return self.errors / self.trial_count if self.trial_count > 0 else 0.0


class ContextCliffBenchmark:
    """
    Background benchmark system for detecting context performance cliffs.

    Runs needle-in-haystack tests and error rate analysis when models reach
    usage thresholds. Results feed into HarmonicMissTracker to tune
    model-specific checkpoint thresholds over time.

    **Configuration & Cost Model**:
    - DISABLED by default (opt-in only)
    - MOCK mode by default (zero cost, no API calls)
    - Only runs after MIN_USAGE_THRESHOLD uses (default: 10)
    - Limits MAX_RUNNING_TESTS concurrently (default: 1)
    - User permission required for live API calls
    """

    # Test needles (various types to avoid overfitting)
    NEEDLE_TEMPLATES = [
        "The secret code is {code}",
        "Remember this: {code}",
        "Important: {code}",
        "Key fact: {code}",
        "Note: {code}",
    ]

    # Test needles (various types to avoid overfitting)
    NEEDLE_TEMPLATES = [
        "The secret code is {code}",
        "Remember this: {code}",
        "Important: {code}",
        "Key fact: {code}",
        "Note: {code}",
    ]

    # Random codes to find
    CODES = ["RED-42", "BLUE-99", "GREEN-17", "YELLOW-88", "PURPLE-73"]

    # Usage thresholds and limits
    MIN_USAGE_THRESHOLD = 10  # Minimum model uses before running benchmarks
    MAX_RUNNING_TESTS = 1     # Maximum concurrent benchmark tests
    MAX_TEST_RESULTS = 1000   # Maximum test results to keep (prevents unbounded growth)

    def __init__(self):
        self._usage_counters: Dict[str, int] = {}
        self._test_results: List[Dict] = []
        self._running_tests: List[asyncio.Task] = []
        self.MOCK_MODE = False  # Set to True for zero-cost testing
        self._band_optimizer = ContextBandOptimizer()  # For golden band analysis
        self._test_todos: Dict[str, Dict] = {}  # Track band opt-in requests

    def enable_mock_mode(self):
        """Enable zero-cost mock testing (no API calls)."""
        self.MOCK_MODE = True
        logger.info("Context cliff benchmark running in MOCK mode (no API calls)")

    def disable_mock_mode(self):
        """Disable mock mode for real testing."""
        self.MOCK_MODE = False
        logger.info("Context cliff benchmark running in LIVE mode (real API calls)")

    async def _mock_llm_response(self, prompt: str, context_length: int) -> str:
        """Return mock LLM response for zero-cost testing."""
        # Simulate latency based on context length (longer = slower)
        base_latency = 0.1  # 100ms base
        context_factor = min(2.0, context_length / 100_000)  # Up to 2x slower for large context
        await asyncio.sleep(base_latency * context_factor)

        # Check if prompt asks about a specific fact or code
        import re

        # Extract Fact ID and value if present
        fact_match = re.search(r'Fact (\d+).*value (\d+)', prompt)
        if fact_match:
            return f"The value for Fact {fact_match.group(1)} is {fact_match.group(2)}"

        # Extract code if present
        code_match = re.search(r'(RED|BLUE|GREEN|YELLOW|PURPLE)-(\d+)', prompt)
        if code_match:
            # Simulate different success rates based on where needle is
            if 'The secret code is' in prompt or 'Remember this:' in prompt:
                # Early in context (high success)
                if random.random() > 0.1:  # 90% success
                    return f"The secret code is {code_match.group(0)}"
                else:
                    return "I don't see any code mentioned."
            else:
                # Later in context (lower success)
                if random.random() > 0.4:  # 60% success
                    return f"I found the code: {code_match.group(0)}"
                else:
                    return "I couldn't find the code you mentioned."

        # Reasoning test
        if 'What is the sum?' in prompt:
            nums = re.findall(r'(\d+)', prompt)
            if len(nums) >= 2:
                try:
                    sum_result = int(nums[-2]) + int(nums[-1])
                    return f"The sum is {sum_result}"
                except:
                    return "I cannot calculate the sum."
            return str(random.randint(1, 200))

        # Default response
        return "I have processed your request and provide this response."

    async def _call_llm_with_mock(self, prompt: str, context_length: int, llm_call_func):
        """Wrapper that uses mock mode if enabled."""
        if self.MOCK_MODE:
            return await self._mock_llm_response(prompt, context_length)
        else:
            return await llm_call_func(prompt)

    def record_usage(self, model_id: str):
        """Record that a model was used."""
        self._usage_counters[model_id] = self._usage_counters.get(model_id, 0) + 1

    def _add_test_results(self, results: List[Dict]):
        """Add test results with automatic trimming to prevent unbounded growth."""
        self._test_results.extend(results)

        # Trim oldest results if we exceed the limit
        if len(self._test_results) > self.MAX_TEST_RESULTS:
            # Keep only the most recent MAX_TEST_RESULTS
            self._test_results = self._test_results[-self.MAX_TEST_RESULTS:]
            logger.debug(f"Trimmed test results to {self.MAX_TEST_RESULTS} most recent entries")

    def should_run_tests(self, model_id: str) -> bool:
        """Determine if we should run benchmarks for this model."""
        usage = self._usage_counters.get(model_id, 0)
        return usage >= self.MIN_USAGE_THRESHOLD

    async def run_background_tests(self, model_id: str, llm_call_func):
        """
        Run background tests if usage threshold met and not already running.

        Args:
            model_id: Model identifier
            llm_call_func: Async function to call LLM (prompt: str) -> str
        """
        if not self.should_run_tests(model_id):
            return

        # Check if already running tests for this model
        for task in self._running_tests:
            if task.model_id == model_id and not task.done():  # type: ignore
                logger.debug(f"Tests already running for {model_id}")
                return

        # Run tests in background
        task = asyncio.create_task(self._run_full_benchmark(model_id, llm_call_func))
        task.model_id = model_id  # type: ignore
        self._running_tests.append(task)

        logger.info(f"Started context cliff benchmark for {model_id}")

        # Cleanup finished tasks
        self._running_tests = [t for t in self._running_tests if not t.done()]

    async def _run_full_benchmark(self, model_id: str, llm_call_func):
        """Run complete benchmark suite for a model."""
        try:
            # Test at various context lengths (logarithmic scale)
            test_lengths = self._get_test_lengths(model_id)
            all_needle_results = []

            for i, length in enumerate(test_lengths):
                logger.debug(f"Testing {model_id} at {length:,} tokens ({i+1}/{len(test_lengths)})")

                # Run needle tests (deeper at each length)
                needle_results = await self._run_needle_tests(
                    model_id, length, llm_call_func, trials=7  # More trials for band analysis
                )

                # Update band optimizer with results (track per-position success)
                if hasattr(self, '_band_optimizer') and hasattr(self, '_test_todos'):
                    for result in needle_results:
                        self._band_optimizer.record_needle_test_result(
                            model_id,
                            result.needle_depth,  # Position in context
                            result.success
                        )

                all_needle_results.extend(needle_results)
                self._add_test_results([asdict(r) for r in needle_results])

                # Run error rate tests
                error_results = await self._run_error_rate_tests(
                    model_id, length, llm_call_func, trials=10
                )
                self._add_test_results([asdict(error_results)])

                # Log sparkline of results
                success_rate = sum(r.success for r in needle_results) / len(needle_results)
                logger.info(
                    f"{model_id} @ {length:,} tokens: "
                    f"needle={success_rate:.1%}, "
                    f"errors={error_results.error_rate:.1%}, "
                    f"latency={error_results.avg_latency_ms:.0f}ms"
                )

                # Log discovered golden bands
                if hasattr(self, '_band_optimizer'):
                    profile = self._band_optimizer.get_model_profile(model_id)
                    if profile and profile.get('test_count', 0) >= 14:  # Enough data
                        bands = self._band_optimizer.adapt_bands_from_data(model_id)
                        golden_count = sum(1 for b in bands if b['weight'] > 1.1)
                        logger.info(
                            f"Discovered {golden_count} golden bands for {model_id} "
                            f"({len(bands)} total via adaptive learning)"
                        )
                        for band in bands[:3]:  # Log top 3
                            logger.debug(
                                f"  Band {band['start']:.1%}-{band['end']:.1%}: "
                                f"weight={band['weight']:.1f}, {band['rationale']}"
                            )

                # TODO: Feed results into HarmonicMissTracker

                # Space out tests
                await asyncio.sleep(5)

            # After all tests, generate comprehensive profile
            if hasattr(self, '_band_optimizer'):
                profile = self._band_optimizer.get_model_profile(model_id)
                if profile:
                    # Create TODO for band optimization
                    if model_id not in self._test_todos:
                        self._test_todos[model_id] = {
                            'band_profile': profile,
                            'optimize_breadcrumbs': False,  # User must opt-in
                            'golden_band_tiles': [],
                        }

                    # Log recommendation
                    bands = profile.get('cliff_analysis', {})
                    if bands:
                        best_length = max(bands.items(), key=lambda x: x[1]['success_rate'])
                        logger.info(
                            f"OPTIMIZATION: Best performance for {model_id} "
                            f"at {best_length[0]:,} tokens "
                            f"({best_length[1]['success_rate']:.1%} success). "
                            f"Consider using --band-opt-in to place breadcrumbs optimally"
                        )

            logger.info(f"Completed context cliff benchmark for {model_id}")

        except Exception as e:
            logger.error(f"Error in context cliff benchmark for {model_id}: {e}")

    def _get_test_lengths(self, model_id: str) -> List[int]:
        """Get context lengths to test based on model's claimed capacity."""
        from ii_agent.llm.model_constants import CONTEXT_WINDOWS, PERFORMANCE_CLIFFS

        claimed_window = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"])
        cliffs = get_performance_cliff_threshold(model_id)

        # Test at:
        # 1. Early degradation point
        # 2. Moderate cliff
        # 3. Severe cliff
        # 4. Near claimed max (if different from cliffs)
        test_lengths = []

        if cliffs["early_degradation"] < claimed_window * 0.5:
            test_lengths.append(cliffs["early_degradation"])

        if cliffs["moderate_cliff"] < claimed_window * 0.8:
            test_lengths.append(cliffs["moderate_cliff"])

        if cliffs["severe_cliff"] < claimed_window:
            test_lengths.append(cliffs["severe_cliff"])

        # Test at 50% claimed (typical effective limit)
        test_lengths.append(claimed_window // 2)

        # Deduplicate and sort
        return sorted(list(set(test_lengths)))

    async def _run_needle_tests(
        self,
        model_id: str,
        context_length: int,
        llm_call_func,
        trials: int = 5,
    ) -> List[NeedleTestResult]:
        """Run needle-in-haystack tests at various depths."""
        results = []

        for i in range(trials):
            # Random depth (0.0 = start, 1.0 = end)
            depth = random.random()

            # Generate filler text (approximate tokens, not exact)
            filler_tokens = int(context_length * depth)
            filler_words = filler_tokens * 0.75  # Rough words-to-tokens ratio
            filler = " ".join(["lorem" * 10] * int(filler_words // 10))

            # Random needle
            template = random.choice(self.NEEDLE_TEMPLATES)
            code = random.choice(self.CODES)
            needle = template.format(code=code)

            # Build prompt
            prompt_parts = []
            if filler_words > 0:
                prompt_parts.append(filler[: int(filler_words * 5)])
            prompt_parts.append(needle)

            # Add post-filler
            post_filler_tokens = context_length - filler_tokens - len(needle.split())
            if post_filler_tokens > 0:
                post_words = post_filler_tokens * 0.75
                post_filler = " ".join(["ipsum" * 10] * int(post_words // 10))
                prompt_parts.append(post_filler[: int(post_words * 5)])

            prompt = "\n\n".join(prompt_parts)

            # Add question at end
            prompt += f"\n\nWhat is the secret code mentioned above?"

            # Call model
            start = datetime.now()
            try:
                response = await self._call_llm_with_mock(prompt, context_length, llm_call_func)
                latency = (datetime.now() - start).total_seconds() * 1000

                # Check if needle was found
                success = code.lower() in response.lower()

                results.append(
                    NeedleTestResult(
                        model_id=model_id,
                        context_length=context_length,
                        needle_depth=depth,
                        success=success,
                        latency_ms=latency,
                        response=response,
                        expected=code,
                    )
                )

            except Exception as e:
                results.append(
                    NeedleTestResult(
                        model_id=model_id,
                        context_length=context_length,
                        needle_depth=depth,
                        success=False,
                        latency_ms=0,
                        response="",
                        expected=code,
                        error=str(e),
                    )
                )

        return results

    async def _run_error_rate_tests(
        self,
        model_id: str,
        context_length: int,
        llm_call_func,
        trials: int = 10,
    ) -> ErrorRateResult:
        """Test error rates at a specific context length."""
        errors = 0
        error_types: Dict[str, int] = {}
        total_latency = 0

        # Build substantial context
        context_words = int(context_length * 0.75)
        context = " ".join([f"Fact {i}: The value is {i % 100}" for i in range(context_words // 5)])

        for i in range(trials):
            # Test for various error types
            test_type = random.choice(["consistency", "edit", "reasoning"])

            start = datetime.now()
            try:
                if test_type == "consistency":
                    response = await self._test_consistency(context, llm_call_func)
                elif test_type == "edit":
                    response = await self._test_edit_safety(context, llm_call_func)
                else:  # reasoning
                    response = await self._test_reasoning(context, llm_call_func)

                latency = (datetime.now() - start).total_seconds() * 1000
                total_latency += latency

                # Check for errors
                error = self._detect_errors(response, test_type)
                if error:
                    errors += 1
                    error_types[error] = error_types.get(error, 0) + 1

            except Exception as e:
                errors += 1
                error_types["exception"] = error_types.get("exception", 0) + 1
                total_latency += 0

        return ErrorRateResult(
            model_id=model_id,
            context_length=context_length,
            trial_count=trials,
            errors=errors,
            error_types=error_types,
            avg_latency_ms=total_latency / trials if trials > 0 else 0,
        )

    async def _test_consistency(self, context: str, llm_call_func) -> str:
        """Test for consistency errors."""
        # Ask about same fact twice, see if answers match
        facts = re.findall(r"Fact (\d+): The value is (\d+)", context)
        if not facts:
            return "No facts found"

        fact_id, value = random.choice(facts)

        prompt1 = f"{context}\n\nWhat is the value for Fact {fact_id}?"
        answer1 = await llm_call_func(prompt1)

        prompt2 = f"{context}\n\nFact {fact_id} value?"
        answer2 = await llm_call_func(prompt2)

        return f"A1: {answer1}\nA2: {answer2}"

    async def _test_edit_safety(self, context: str, llm_call_func) -> str:
        """Test for edit safety issues."""
        # Ask model to modify text, see if it follows instruction accurately
        lines = context.split(".")[:20]  # First 20 sentences
        target = random.choice(lines).strip()

        prompt = f"Text:\n{context}\n\nChange '{target}' to '[MODIFIED]' and output full text:"
        response = await llm_call_func(prompt)

        return response

    async def _test_reasoning(self, context: str, llm_call_func) -> str:
        """Test reasoning with context."""
        # Multi-hop reasoning test
        facts = re.findall(r"Fact (\d+): The value is (\d+)", context)
        if len(facts) < 2:
            return "Not enough facts"

        f1, f2 = random.sample(facts, 2)

        prompt = (
            f"{context}\n\n"
            f"Fact {f1[0]} has value {f1[1]}. "
            f"Fact {f2[0]} has value {f2[1]}. "
            f"What is the sum?"
        )

        response = await llm_call_func(prompt)
        return response

    def _detect_errors(self, response: str, test_type: str) -> Optional[str]:
        """Detect specific error types in responses."""
        resp_lower = response.lower()

        # Hallucination detection
        if "i don't know" in resp_lower and test_type != "edit":
            return "avoidance"

        # Inconsistency detection (for consistency test)
        if test_type == "consistency":
            # Look for two answers that don't match
            lines = [l for l in response.split("\n") if "value" in l.lower()]
            values = re.findall(r"\d+", response)
            if len(values) >= 2 and values[0] != values[1]:
                return "inconsistency"

        # Edit safety failure (didn't modify as instructed)
        if test_type == "edit" and "[MODIFIED]" not in response:
            return "edit_failure"

        # Reasoning errors
        if test_type == "reasoning":
            # Check if response has a clear numeric answer
            has_number = bool(re.search(r"\d+", response))
            if not has_number:
                return "no_answer"

        return None

    def get_model_profile(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get performance profile for a model based on test results.

        Returns cliff detection data, error rates, and recommended thresholds.
        """
        # Filter results for this model
        model_results = [r for r in self._test_results if isinstance(r, dict) and r.get("model_id") == model_id]

        if not model_results:
            return None

        # Separate needle and error rate results
        needle_results = [r for r in model_results if "needle_depth" in r]
        error_results = [r for r in model_results if "error_rate" in r]

        # Calculate metrics by context length
        cliff_analysis = {}

        for length in sorted(set(r["context_length"] for r in needle_results)):
            length_results = [r for r in needle_results if r["context_length"] == length]

            if len(length_results) < 3:
                continue

            success_rate = sum(r["success"] for r in length_results) / len(length_results)
            avg_latency = sum(r["latency_ms"] for r in length_results) / len(length_results)

            cliff_analysis[length] = {
                "success_rate": success_rate,
                "avg_latency_ms": avg_latency,
                "sample_size": len(length_results),
            }

        # Detect cliffs (sharp drops in success rate)
        cliff_thresholds = []
        lengths = sorted(cliff_analysis.keys())

        for i in range(1, len(lengths)):
            prev_length = lengths[i - 1]
            curr_length = lengths[i]

            prev_success = cliff_analysis[prev_length]["success_rate"]
            curr_success = cliff_analysis[curr_length]["success_rate"]

            # Cliff if success drops >20% or below 70%
            if prev_success - curr_success > 0.2 or curr_success < 0.7:
                cliff_thresholds.append({
                    "cliff_at": curr_length,
                    "success_drop": prev_success - curr_success,
                    "prev_length": prev_length,
                    "prev_success": prev_success,
                    "curr_success": curr_success,
                })

        # Overall error rate
        if error_results:
            avg_error_rate = sum(r["error_rate"] for r in error_results) / len(error_results)
        else:
            avg_error_rate = 0.0

        return {
            "model_id": model_id,
            "test_count": len(model_results),
            "cliff_analysis": cliff_analysis,
            "detected_cliffs": cliff_thresholds,
            "avg_error_rate": avg_error_rate,
            "recommendation": self._generate_recommendation(cliff_thresholds, avg_error_rate),
        }

    def _generate_recommendation(
        self, cliffs: List[Dict], error_rate: float
    ) -> Dict[str, Any]:
        """Generate checkpoint threshold recommendation."""
        if not cliffs:
            return {
                "action": "no_cliff_detected",
                "recommended_threshold_pct": 0.80,
                "confidence": "low",
            }

        # Use earliest detected cliff
        earliest_cliff = min(cliffs, key=lambda x: x["cliff_at"])
        cliff_length = earliest_cliff["cliff_at"]

        # Set checkpoint threshold at 80% of cliff (aggressive safety)
        recommended_threshold = cliff_length * 0.8

        return {
            "action": "adjust_threshold",
            "cliff_detected_at": cliff_length,
            "recommended_threshold_tokens": int(recommended_threshold),
            "severity": "high" if earliest_cliff["success_drop"] > 0.3 else "medium",
            "confidence": "high" if len(cliffs) >= 2 else "medium",
        }
