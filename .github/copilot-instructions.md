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
