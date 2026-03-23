"""conftest.py for tests/ - provide minimal environment for unit tests.

IIAgentConfig requires env vars at module level. We set them here before
any test module is collected.
"""
import os

# Force-set (not setdefault) to ensure these take effect before IIAgentConfig loads.
_TEST_ENV = {
    "LLM_CONFIGS": '{"default":{"api_type":"openai","model":"gpt-4o","api_key":"test-key"}}',
    "RESEARCHER_AGENT_CONFIG": '{"researcher":{},"report_builder":{},"final_report_builder":{}}',
    "FILE_STORE_PATH": "/tmp/ii_agent_test",
    "LOCAL_STORAGE_PATH": "/tmp/ii_agent_test/storage",
    "DATABASE_URL": "postgresql+asyncpg://iiagent:iiagent@localhost:5433/iiagentdev",
}

for key, val in _TEST_ENV.items():
    if key not in os.environ:
        os.environ[key] = val
