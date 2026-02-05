# Skill Template

A standardized template for creating new ii-agent skills.

---

## SKILL.md Template

Every skill should have a `SKILL.md` file in its root folder with the following structure:

```markdown
---
name: My Skill Name
description: Brief description of what this skill does
version: 1.0.0
author: Your Name
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# [Skill Name]

[One paragraph description of the skill's purpose and capabilities]

## Capabilities

- [Capability 1]
- [Capability 2]
- [Capability 3]

## Prerequisites

- [Required API key or credential]
- [Required Python package]
- [Required external service]

## Configuration

### Credentials

Store credentials in `Config/` (never commit to git):

| File | Purpose |
|------|---------|
| `Config/my-api-key.txt` | API key for service X |

### Settings

```python
# config.py (gitignored)
API_KEY = "your-api-key"
BASE_URL = "https://api.example.com"
```

## Usage

### Basic Usage

```python
from ii_skills.my_skill import MySkill

skill = MySkill()
result = await skill.run(input_data)
```

### CLI Usage

```bash
python -m ii_skills.my_skill.main --input "data"
```

## Commands

| Command | Description |
|---------|-------------|
| `"do X"` | Performs action X |
| `"analyze Y"` | Analyzes input Y |

## Output

### Files Generated

| Output | Location | Description |
|--------|----------|-------------|
| Report | `outputs/report.pdf` | Generated report |
| Data | `outputs/data.json` | Raw data export |

### Example Output

```json
{
  "status": "success",
  "result": { ... }
}
```

## Integration

### With Other Skills

```python
from ii_skills.other_skill import OtherSkill

# Combine with other skill
```

### With Shared Infrastructure

```python
from ii_skills.shared import TelemetryLogger, track_tool_execution

# Use telemetry for tracking
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| API timeout | Increase timeout or retry |
| Auth error | Check credentials in Config/ |

## Changelog

### v1.0.0 (YYYY-MM-DD)
- Initial release
```

---

## Folder Structure Template

```
src/ii_skills/my_skill/
├── __init__.py           # Package exports
├── SKILL.md              # This documentation
├── config.py             # Configuration (gitignored)
├── config.py.example     # Example config (committed)
├── main.py               # Entry point / CLI
├── core.py               # Core logic
├── modules/              # Modular components
│   ├── __init__.py
│   ├── module_a.py
│   └── module_b.py
├── templates/            # Templates (Excel, PPT, etc.)
│   └── template.xlsx
├── outputs/              # Generated outputs (gitignored)
│   └── .gitkeep
└── tests/                # Unit tests
    └── test_core.py
```

---

## Required Files

### `__init__.py`

```python
"""
[Skill Name]

[Brief description]
"""

from my_skill.core import MySkillClass

__all__ = ["MySkillClass"]
__version__ = "1.0.0"
```

### `config.py.example`

```python
"""
Example configuration for [Skill Name].

Copy this file to config.py and fill in your credentials.
"""

# API Configuration
API_KEY = "your-api-key-here"
API_BASE_URL = "https://api.example.com"

# Feature Flags
ENABLE_CACHING = True
DEBUG_MODE = False
```

### `main.py`

```python
"""
CLI entry point for [Skill Name].

Usage:
    python -m ii_skills.my_skill.main [options]
"""

import asyncio
import argparse
from my_skill.core import MySkillClass


async def main():
    parser = argparse.ArgumentParser(description="[Skill Name]")
    parser.add_argument("--input", required=True, help="Input data")
    args = parser.parse_args()

    skill = MySkillClass()
    result = await skill.run(args.input)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Integration Checklist

When creating a new skill:

- [ ] Create folder structure
- [ ] Write `SKILL.md` documentation
- [ ] Create `config.py.example`
- [ ] Add to `src/ii_skills/__init__.py` exports
- [ ] Add to `CLAUDE.md` skill reference
- [ ] Add to `TASK_REFERENCE.md`
- [ ] Update `docs/skills/README.md`
- [ ] Write basic tests
- [ ] Test manually end-to-end

---

## Best Practices

### 1. Configuration

- Never hardcode credentials
- Use `Config/` for secrets
- Provide `.example` config files

### 2. Error Handling

- Use specific exception types
- Log errors with context
- Provide helpful error messages

### 3. Output

- Use consistent output locations
- Clean up temporary files
- Support multiple output formats

### 4. Documentation

- Keep SKILL.md updated
- Include usage examples
- Document all commands

### 5. Testing

- Write unit tests for core logic
- Include integration tests
- Test error paths

---

## Example Skills

Reference these existing skills for patterns:

| Skill | Good For |
|-------|----------|
| `ib_toolkit` | Multi-phase orchestration, Excel/PPT generation |
| `ir_toolkit` | Module-based analysis, paired outputs |
| `networth_newsletter` | Scheduled tasks, email integration |
| `market_newsletter` | API integration, news aggregation |
| `health_dashboard` | OAuth flows, external service integration |

---

*This template is part of the II-Agent Skills System.*
