# Excel Backup Templates for Slide Generation

This folder contains 18 Excel template files with sample data and charts that serve as data backups for PowerPoint slide generation.

## Template Files

| File | Slide Template | Description |
|------|----------------|-------------|
| `03_peer_benchmarking.xlsx` | Peer Benchmarking Bar Chart | Peer comparison with bar chart |
| `04_comps_table.xlsx` | Comprehensive Comps Table | Trading comps with multiples |
| `05_time_series.xlsx` | Time Series Line Chart | Date series with line chart |
| `06_before_after.xlsx` | Before/After Comparison | KPI comparison table |
| `07_sources_uses.xlsx` | Sources & Uses | Transaction structure |
| `08_scenario_analysis.xlsx` | Scenario Analysis | Bull/Base/Bear scenarios |
| `09_horizontal_bar_pie.xlsx` | Horizontal Bar + Pie | Rankings with pie chart |
| `10_gantt_chart.xlsx` | Gantt Chart / Timeline | Project milestones |
| `11_heat_map.xlsx` | Heat Map / Performance Matrix | Color-coded performance |
| `12_portfolio_valuations.xlsx` | Portfolio Valuations | Investment returns table |
| `14_debt_benchmarking.xlsx` | Debt Structure Benchmarking | Capital structure comparison |
| `16_achievement_summary.xlsx` | 4-Quadrant Achievement | KPI targets vs actuals |
| `17_track_record.xlsx` | Track Record CAGR | Historical performance with chart |
| `19_exit_summary.xlsx` | Exit Strategy Grid | Exit returns summary |
| `22_debt_maturity.xlsx` | Debt Maturity Profile | Maturity schedule with chart |
| `23_value_bridge.xlsx` | Value Creation Bridge | Waterfall components |
| `25_deal_showcase.xlsx` | Deal Showcase Grid | Transaction highlights |
| `27_cost_of_capital.xlsx` | Cost of Capital Spectrum | Funding cost comparison |

## Usage

### For Plugin Integration

```python
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "excel_templates"

# Load a template
template_path = TEMPLATES_DIR / "04_comps_table.xlsx"
```

### For Slide Generation

Each Excel file contains:
1. **Data sheet** - Structured data matching the slide layout
2. **Charts** (where applicable) - Pre-formatted charts that can be embedded
3. **Instructions sheet** (some files) - Column definitions and usage notes

### Regenerating Templates

```bash
cd src/ii_skills/shared/excel_templates
python generate_templates.py
```

## File Structure

Each template follows a consistent pattern:

```
Sheet: [Template_Name]
- Row 1: Headers (styled with gray background, white text)
- Row 2+: Sample data (alternating row colors)
- Subject rows: Green background highlighting
- Totals/Summary rows: Bold formatting
```

## Color Coding

| Element | Color | Hex |
|---------|-------|-----|
| Headers | Dark Gray | #4A4A4A |
| Subject/Highlight | Green | #00A651 |
| Alternating Rows | Light Gray | #F0F0F0 |
| Negative Values | Red | #C00000 |

## Related Documentation

- [EXCEL_BACKUP_REFERENCE.md](../../../../docs/skills/EXCEL_BACKUP_REFERENCE.md) - Full column specifications
- [SLIDE_DESIGN_GUIDE.md](../../../../docs/skills/SLIDE_DESIGN_GUIDE.md) - PowerPoint slide templates

---

*Generated: 2026-02-04*
