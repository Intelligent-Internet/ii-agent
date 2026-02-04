# II-Agent Skills System

A modular plugin framework for extending ii-agent capabilities with domain-specific skills.

## Overview

Skills are self-contained modules that provide specialized functionality. Each skill:
- Has its own dependencies and configuration
- Exposes a standard interface for ii-agent to invoke
- Can be enabled/disabled independently
- Maintains its own documentation and templates

## Available Skills

| Skill | Status | Description |
|-------|--------|-------------|
| `ib_toolkit` | ✅ Active | Investment banking presentations, Excel models, deal analysis |
| `market_newsletter` | 🔜 Planned | Daily market news and price tracking |
| `health_dashboard` | 🔜 Planned | WHOOP health metrics integration |
| `memory` | 🔜 Planned | Long-term context and memory management |

## Architecture

```
ii_skills/
├── __init__.py              # Skill registry and base classes
├── README.md                # This file
├── ib_toolkit/              # Investment Banking Toolkit
│   ├── __init__.py          # Skill class and registration
│   ├── README.md            # Skill documentation
│   ├── requirements.txt     # Skill dependencies
│   ├── config.py            # Configuration
│   ├── data_fetcher.py      # Financial data APIs
│   ├── excel_models.py      # Excel model generation
│   ├── pptx_generator.py    # PowerPoint generation
│   ├── modules/             # Analysis modules (M1-M14)
│   ├── templates/           # Slide and model templates
│   └── output/              # Generated files
├── market_newsletter/       # (Coming Soon)
├── health_dashboard/        # (Coming Soon)
└── memory/                  # (Coming Soon)
```

## Usage

### Registering a Skill

Skills are auto-discovered on import. To create a new skill:

```python
from ii_skills import BaseSkill, register_skill

@register_skill
class MySkill(BaseSkill):
    name = "my_skill"
    version = "1.0.0"
    description = "My custom skill"

    def execute(self, action: str, **kwargs):
        if action == "my_action":
            return self._do_something(**kwargs)
        raise NotImplementedError(f"Action '{action}' not implemented")

    def _do_something(self, param1: str) -> dict:
        return {"success": True, "result": param1}
```

### Using a Skill

```python
from ii_skills import get_skill, list_skills

# List available skills
print(list_skills())

# Get a skill instance
toolkit = get_skill("ib_toolkit")

# Execute an action
result = toolkit.execute("create_company_deck", ticker="AAPL")
```

### From ii-agent Core

```python
from ii_skills.ib_toolkit import get_toolkit

toolkit = get_toolkit()
if toolkit.is_ready:
    result = toolkit.execute("fetch_company_data", ticker="NVDA")
```

## Adding Dependencies

Each skill manages its own dependencies via `requirements.txt`. Install all skill dependencies:

```bash
# From ii-agent root
pip install -r src/ii_skills/ib_toolkit/requirements.txt
```

Or add to the main `pyproject.toml` as optional dependencies.

## Configuration

Skills can require configuration (API keys, credentials). Configuration is passed during initialization:

```python
config = {
    "FMP_API_KEY": "your_key_here",
    "OUTPUT_DIR": "/custom/output/path"
}
toolkit = get_skill("ib_toolkit", config=config)
```

## Documentation

Skill documentation is stored in `docs/skills/<skill_name>/`:

```
docs/skills/
└── ib_toolkit/
    ├── BEST_PRACTICES.md
    ├── SLIDE_TEMPLATES.md
    ├── ORCHESTRATION_FRAMEWORK.md
    ├── PROMPT_LIBRARY.md
    ├── CASE_INTAKE_PROTOCOL.md
    └── CLAUDE_FOR_EXCEL_PROMPTS.md
```

## Creating a New Skill

1. Create directory: `src/ii_skills/my_skill/`
2. Create `__init__.py` with skill class decorated by `@register_skill`
3. Create `README.md` documenting the skill
4. Create `requirements.txt` with dependencies
5. Add documentation to `docs/skills/my_skill/`
6. Test: `from ii_skills import get_skill; get_skill("my_skill")`

## Source

Skills system adapted from the Claire Agent System, integrating:
- Investment Banking Toolkit (BCI Growth Equity, Northleaf PE case studies)
- Orchestration Framework (Buyside Agent Resources 52-prompt system)
- Middle Market Case Study Protocol

---

*Version: 1.0.0*
*Last Updated: 2026-02-04*
