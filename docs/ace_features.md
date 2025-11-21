# ACE Context Window & REPL Features

This document describes the ACE (Adaptive Context Engine) features added to the REPL and server.

## REPL /context command

- Use `/context` to inspect the current session context and token usage. It shows:
  - Total tokens in your session
  - Model's context window
  - Model-specific checkpoint threshold
  - Performance cliffs (early_degradation, moderate_cliff, severe_cliff)
  - Use `/harmonic` to view harmonic miss stats (error counts and context pressure)

## Local token counting

- The REPL uses a `TokenCounter` to estimate tokens more accurately (handles text and image payloads).
- Local session will warn when approaching the context window and will locally reduce older messages when above 90% of the window.

## Server-side ContextWindowManager

- The server runs context maintenance after each agent run:
  - Creates checkpoints when thresholds are reached (e.g., model-specific thresholds)
  - Creates tiles for future context when dumping at ~33% of model context window
  - Summarizes conversation automatically at ~95% usage (placeholder summarization for now)
  - Publishes events for checkpoints, tile generation, summary creation, and performance warnings
  - Uses persistent `HarmonicMissTracker` for recording and reporting harmonic misses (edit slips, hallucinations, inconsistencies). The harmonic tracker can recommend safer checkpoint thresholds by observing error clusters.

## Harmonic misses and cliffs

- The ContextWindowManager tracks "harmonic misses" per model to monitor context pressure-related errors.
- The server publishes monitoring events for harmonic miss stats and performance warnings.

## Notes & Next Steps

- The golden band optimizer and background cliff benchmark system are implemented; tile generation and checkpoint persistence are implemented.
- If you'd like more aggressive behavior (auto-evict, automatic summarization using a real LLM), we can wire in additional LLM calls and policies.

For more details, see `src/ii_agent/server/chat/context_manager.py` and the REPL implementation at `src/ii_agent/cli/repl.py`.
