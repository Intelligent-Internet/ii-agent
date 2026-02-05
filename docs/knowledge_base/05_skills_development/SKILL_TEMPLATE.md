# How to Build a New Skill

## Quick Start

### 1. Create the skill directory

```
src/ii_skills/your_skill_name/
├── __init__.py       # Skill class with @register_skill
├── config.py         # Optional: skill-specific configuration
└── README.md         # Optional: skill documentation
```

### 2. Implement the skill class

```python
# src/ii_skills/your_skill_name/__init__.py

from typing import Dict, List, Optional
from ii_skills import BaseSkill, register_skill

__version__ = "1.0.0"


@register_skill
class YourSkill(BaseSkill):
    name = "your_skill_name"       # Must match directory name
    version = __version__
    description = "What this skill does in one sentence"

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)

    def validate_config(self) -> List[str]:
        """Return list of config issues (empty = OK)."""
        issues = []
        # Example: check for required API key
        # if not self.config.get("api_key"):
        #     issues.append("api_key is required")
        return issues

    def get_capabilities(self) -> List[str]:
        """Return list of action names this skill supports."""
        return [
            "action_one",
            "action_two",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Route action to handler method."""
        if action == "action_one":
            return self._action_one(**kwargs)
        elif action == "action_two":
            return self._action_two(**kwargs)
        else:
            raise NotImplementedError(f"Action '{action}' not implemented")

    def _action_one(self, param_a: str, param_b: int = 10) -> Dict:
        """Implement action_one."""
        result = do_something(param_a, param_b)
        return {"success": True, "data": result}

    def _action_two(self, input_data: Dict) -> Dict:
        """Implement action_two."""
        output = process(input_data)
        return {"success": True, "output": output}
```

### 3. That's it. The bridge auto-discovers it.

When `ii_skills` is imported, `discover_skills()` walks the directory
and imports your module. The `@register_skill` decorator adds it to
the registry. The bridge layer wraps it as a `BaseTool`.

## Conventions

### Naming
- Directory name = skill `name` attribute = how the LLM sees it
- Tool name will be `skill_{name}` (e.g., `skill_your_skill_name`)

### Return Format
Always return a dict with at least `{"success": True/False}`:
```python
# Success
{"success": True, "data": {...}}

# Success with file
{"success": True, "output_path": "/path/to/file.xlsx"}

# Failure
{"success": False, "error": "What went wrong"}
```

### File Output
- Use `Path(__file__).parent / "output"` for generated files
- Create the output directory in `__init__`: `self.OUTPUT_DIR.mkdir(exist_ok=True)`
- Return the absolute path in the result dict

### Config
- Skills should work with zero config when possible
- Use `validate_config()` to report missing optional keys (not crash)
- Read from `self.config` dict or environment variables

### Shared Infrastructure
Skills can use any service from `ii_skills.shared`:
```python
from ii_skills.shared import get_telemetry_logger, get_datastore

# Telemetry
logger = get_telemetry_logger()
async with logger.run_context(run_type="my_skill") as ctx:
    ctx.log_event("started")

# Data store
store = get_datastore()
data = await store.get_holdings(user_id="...")
```

## Testing Your Skill

Add fixtures to `tests/integration/conftest.py`:
```python
@pytest.fixture
def your_skill():
    from ii_skills import get_skill
    skill = get_skill("your_skill_name")
    if skill is None:
        pytest.skip("your_skill_name not available")
    skill.initialize()
    return skill
```

Add tests to `tests/integration/test_your_skill.py`:
```python
class TestYourSkill:
    def test_action_one(self, your_skill):
        result = your_skill.execute("action_one", param_a="test")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_via_bridge(self, your_skill, workspace_path):
        from ii_skills.bridge import SkillTool
        tool = SkillTool(your_skill, workspace_path=workspace_path)
        result = await tool.execute({
            "action": "action_one",
            "params": {"param_a": "test"},
        })
        assert result.is_error is not True
```
