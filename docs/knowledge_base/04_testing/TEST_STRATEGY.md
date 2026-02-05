# Test Strategy

## Test Layers

```
┌───────────────────────────────────────────┐
│         E2E Tests (Manual / Playwright)    │  User → Desktop App → Output File
├───────────────────────────────────────────┤
│         Integration Tests (pytest)         │  Bridge → Skill → Output
├───────────────────────────────────────────┤
│         Unit Tests (pytest)                │  Individual functions
└───────────────────────────────────────────┘
```

## Current Test Coverage

| Area | Location | Status |
|------|----------|--------|
| Message history | `tests/test_message_history.py` | Existing |
| LLM context | `tests/llm/context_manager/` | Existing |
| Tool execution | `tests/tools/` | Existing |
| **Skill bridge** | `tests/integration/test_skill_bridge.py` | **NEW** |
| **IB toolkit E2E** | `tests/integration/test_ib_toolkit_e2e.py` | **Planned** |
| **IR toolkit E2E** | `tests/integration/test_ir_toolkit_e2e.py` | **Planned** |

## Running Tests

```bash
# All tests
uv run pytest

# Integration tests only
uv run pytest tests/integration/

# Specific test file
uv run pytest tests/integration/test_skill_bridge.py -v

# With output
uv run pytest tests/integration/ -v -s
```

## Test Fixtures

Shared fixtures are in `tests/integration/conftest.py`:

| Fixture | Returns |
|---------|---------|
| `ib_toolkit` | Initialized IBToolkitSkill instance |
| `ir_toolkit` | Initialized IRToolkitSkill instance |
| `skill_tool_ib` | SkillTool wrapping IB Toolkit |
| `all_skill_tools` | List of all available SkillTools |
| `sample_lbo_params` | Standard LBO test parameters |
| `sample_company_params` | Standard company test parameters |
| `sample_capital_structure_params` | Capital structure test parameters |
| `sample_qoe_params` | Quality of earnings test parameters |
| `test_output_dir` | Temporary directory for generated files |
| `workspace_path` | Simulated workspace path |

## What to Test for Each New Skill

When adding a new skill, create integration tests that verify:

1. **Discovery** — Skill is found by `discover_skills()`
2. **Registration** — Skill appears in `_SKILLS` registry
3. **Wrapping** — `SkillTool` correctly exposes the skill's capabilities
4. **Execution** — Each action produces expected output type
5. **Error handling** — Invalid inputs return errors, not crashes
6. **File generation** — Output files exist and are valid (not empty)

## Priority Test Cases

### Must-have (Phase 1)
- [x] Skill discovery works
- [x] Bridge wrapping produces valid BaseTool
- [x] LBO quick analysis returns IRR/MOIC
- [x] LBO sensitivity returns matrix
- [x] Capital structure analysis works
- [x] QoE analysis works
- [x] Excel generation produces file
- [x] Error handling for invalid inputs

### Should-have (Phase 2)
- [ ] Slide generation produces valid PPTX
- [ ] Full deck generation works
- [ ] Data fetcher returns company data
- [ ] IR toolkit LP update generation
- [ ] Multiple skills registered simultaneously
- [ ] Skill tool works within AgentToolManager.run_tools_batch()

### Nice-to-have (Phase 3)
- [ ] Deal orchestrator multi-phase execution
- [ ] Telemetry logging during skill execution
- [ ] Budget enforcement during long operations
- [ ] Memory service integration
- [ ] Output file copy to workspace
