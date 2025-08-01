# Plan Mode Documentation

Plan Mode introduces a two-phase development approach to ii-agent CLI, inspired by Gemini CLI's planning system. It separates the planning phase from the implementation phase to enable better preparation, review, and execution of complex features.

## Overview

Plan Mode consists of two main commands:
- `/plan` - Generate detailed implementation plans (read-only analysis)
- `/implement` - Execute pre-existing plans step-by-step

## Quick Start

### 1. Generate a Plan
```bash
/plan Add user authentication with JWT tokens
```

This will:
- Activate read-only analysis mode
- Investigate your codebase structure
- Generate a comprehensive implementation plan
- Save the plan to `plans/` directory

### 2. Review the Plan
```bash
cat plans/a1b2c3d4_add_user_authentication.md
```

The plan includes:
- Codebase analysis findings
- Step-by-step implementation strategy
- Risk assessment and mitigation
- Testing approach
- Timeline estimates

### 3. Execute the Plan
```bash
/implement a1b2c3d4
```

This will:
- Load the implementation plan
- Execute steps one by one
- Request confirmation for major steps
- Track progress and update plan status

## Commands Reference

### `/plan <feature_description>`
Generate a detailed implementation plan for a feature.

**Examples:**
```bash
/plan Implement real-time chat with WebSockets
/plan Add dark mode toggle to UI components  
/plan Create user dashboard with analytics
```

**Options:**
- `/plan --list` - List all existing plans
- `/plan --help` - Show detailed help

### `/implement <plan_id>`
Execute a pre-existing implementation plan.

**Examples:**
```bash
/implement a1b2c3d4
/implement --list
```

**Options:**
- `/implement --list` - List all available plans
- `/implement --help` - Show detailed help

**Interactive Features:**
- Step-by-step confirmation
- Skip option for individual steps
- Cancel option at any point
- Continue despite failures option

## Plan Workflow

### Phase 1: Planning (`/plan`)
1. **Investigation** - Analyzes existing codebase (read-only)
2. **Analysis** - Understands patterns and architecture
3. **Strategy** - Develops implementation approach
4. **Documentation** - Creates comprehensive plan

### Phase 2: Implementation (`/implement`)
1. **Loading** - Parses plan and extracts steps
2. **Confirmation** - Shows overview and gets approval
3. **Execution** - Runs steps with agent controller
4. **Tracking** - Updates progress and plan status
5. **Completion** - Finalizes and documents results

## Plan Structure

Generated plans include:

### Metadata
- Plan ID, name, description
- Creation and update timestamps
- Current status

### Content Sections
- **Overview** - Feature summary and goals
- **Investigation Summary** - Key codebase findings
- **Implementation Strategy** - Detailed step-by-step approach
- **Technical Details** - Architecture changes and requirements
- **Risk Assessment** - Challenges and mitigation strategies
- **Testing Strategy** - Validation approach
- **Success Criteria** - Definition of completion
- **Timeline Estimate** - Realistic time estimates

## Plan Status States

- **planning** - Plan is being generated
- **ready** - Plan ready for implementation
- **in_progress** - Implementation is running
- **completed** - Implementation finished successfully
- **cancelled** - Implementation was cancelled
- **error** - Implementation encountered errors

## File Structure

```
workspace/
├── plans/
│   ├── .plan_state.json          # Current plan mode state
│   ├── .plans_index.json         # Plan metadata index
│   ├── a1b2c3d4_feature_name.md  # Individual plan files
│   └── ...
```

## Best Practices

### When to Use Plan Mode

**Good Use Cases:**
- Complex features requiring multiple files
- Features touching core architecture
- New functionality requiring research
- Large refactoring projects
- Features with unclear requirements

**Skip Plan Mode For:**
- Simple bug fixes
- Minor text changes
- Well-understood small features
- Quick prototypes

### Planning Tips

1. **Be Specific** - Provide detailed feature descriptions
2. **Review Plans** - Always review generated plans before implementing
3. **Modify Plans** - Edit plan files if adjustments are needed
4. **Use Context** - Run `/plan` when you have good workspace context

### Implementation Tips

1. **Step-by-Step** - Don't rush through confirmations
2. **Monitor Progress** - Watch for errors and address them
3. **Use Skip Wisely** - Skip steps only when appropriate
4. **Save Often** - Progress is automatically saved

## Troubleshooting

### Common Issues

**Plan Generation Fails**
- Ensure agent controller is available
- Check workspace has proper structure
- Verify feature description is clear

**Implementation Errors**
- Review error messages carefully
- Use continue/skip options appropriately
- Check file permissions and dependencies

**Missing Plans**
- Use `/plan --list` to see available plans
- Check `plans/` directory exists
- Verify workspace path is correct

### Recovery

**Interrupted Implementation**
- Implementation progress is automatically saved
- Use `/implement <plan_id>` to resume
- Plan status tracks current state

**Corrupted Plans**
- Plans are stored as readable markdown
- Edit plan files directly if needed
- Use cleanup methods if necessary

## Advanced Usage

### Custom Plan Templates

Plans are generated using templates in `src/ii_agent/cli/templates/`:
- `plan_template.md` - Base plan structure
- `implementation_checklist.md` - Progress tracking template

### Plan State Management

The `PlanStateManager` class provides programmatic access:
```python
from ii_agent.cli.plan_state import PlanStateManager

manager = PlanStateManager(workspace_path)
plans = manager.list_plans()
plan_info = manager.get_plan_info(plan_id)
```

### Integration with Existing Workflow

Plan Mode integrates seamlessly with:
- Existing CLI commands
- State persistence (`--continue`)
- Session management (`--resume`)
- MoA (Mixture-of-Agents) mode

## Examples

### Complete Workflow Example

```bash
# 1. Generate plan
/plan Implement user authentication system with JWT

# 2. Review generated plan
cat plans/a1b2c3d4_implement_user_authentication.md

# 3. Execute plan
/implement a1b2c3d4

# 4. Monitor progress and confirm steps
# (Interactive prompts will guide you)

# 5. Verify completion
/implement --list
```

### Batch Planning

```bash
# Generate multiple plans
/plan Add user registration flow
/plan Implement password reset
/plan Add two-factor authentication
/plan Create admin dashboard

# Review all plans
/plan --list

# Implement in order
/implement a1b2c3d4  # Registration
/implement e5f6g7h8  # Password reset
# ... etc
```

This documentation provides comprehensive guidance for using Plan Mode effectively in your development workflow.