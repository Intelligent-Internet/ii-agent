# Changelog

## collector branch (2025-11-19)

### Features
- **Python 3.14 compatibility**: Forward-compatible pydantic, puremagic instead of imghdr
- **REPL mode**: Interactive CLI with tab completion for model/provider selection
- **NVIDIA provider**: Qwen3-coder-480b default, Bayesian model ranking
- **Memory systems**: Hashtable, memvid QR, DuckDB vector search
- **Installation options**: Full (2GB) or lite (200MB via requirements-lite.txt)

### Implementation
- `src/ii_agent/cli/`: REPL mode entry point and implementation
- `src/ii_agent/db/`: Async SQLite, DuckDB integration
- `src/ii_agent/storage/`: Three memory backend options
- `src/ii_agent/server/api/nvidia_models.py`: NVIDIA model fetching
- `scripts/fetch_nvidia_models.py`: Bayesian ranking script

### Breaking Changes
- Unpinned pydantic (was ==2.11.7, now >=2.11.7)
- Removed deprecated test files

### Documentation
- `docs/INSTALL.md`: Installation guide
- `requirements-lite.txt`: Minimal REPL-only install
