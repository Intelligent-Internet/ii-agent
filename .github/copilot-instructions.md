# Do not use base docker compose commands to do any kind of stack operations.
# Instructions on restarting and rebuilding the stack:
# Use the following tool preferentially and prefer --local mode:
scripts/stack_control.sh

# Other scripts are also available to you under:
scripts/local/*

# Credentials are available in
docker/.stack.env.local

# Python venv is located in
~/workspaces/venvs/ii-agent

# When creating new design docs, place then in docs/design-docs rather than creating them within agentic memory storage.

# When creating new test docs, place then in docs/test-docs rather than creating them within agentic memory storage.

# When creating new implementation docs, place then in docs/impl-docs rather than creating them within agentic memory storage.

# Logging — loguru vs stdlib (READ THIS BEFORE WRITING OR REVIEWING ANY logger.* CALL)
#
# `ii_agent.core.logger` and `loguru.logger` use BRACE-STYLE formatting `{}`.
# `ii_agent_tools.logger` and `ii_server.logger` use STDLIB %-STYLE `%s`.
#
# In a loguru file, `logger.info("foo %s bar", x)` does NOT interpolate. The
# message renders literally as `foo %s bar` and the extra positional arg is
# silently dropped. This has caused production debugging failures multiple
# times (sandbox claim logs showing `row=%s slot=%s session=%s`).
#
# Rules:
#   - In files that import `from ii_agent.core.logger import logger` or
#     `from loguru import logger`: use f-strings or `{var}` placeholders with
#     `.format()`/keyword args. NEVER `%s`, `%d`, `%r` with positional args.
#       OK:  logger.info(f"Claimed slot {slot} for session {sid}")
#       OK:  logger.info("Claimed slot {} for session {}", slot, sid)
#       BAD: logger.info("Claimed slot %s for session %s", slot, sid)
#   - In files that import `from ii_agent_tools.logger import get_logger` or
#     `from ii_server.logger import get_logger`: use stdlib `%s`/`%d` style.
#       OK:  logger.info("Claimed slot %s for session %s", slot, sid)
#   - When migrating a file from stdlib to loguru (or vice versa), audit
#     EVERY `logger.*` call in that file at the same time.
