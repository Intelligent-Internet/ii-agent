# Learning: Professional Slide Design Patterns

**Date:** 2026-02-04
**Category:** new-capability

## What Happened

Analyzed 25+ slides from user's Historical Work folder to extract professional IB/IR slide design patterns:
- TD Securities: Florence Strategic Rationale (2022)
- TD Securities: Northview Acquisition Disposition (2025)
- TD Securities: Spring Living IPO Mandate (2025)
- PropelR Investor Presentation (2025)

## What Was Learned

### Core Design Patterns

1. **Key Takeaway Bar**: Green bar at bottom with italic text summarizing slide insight
2. **Subject Highlighting**: Subject company always in green, peers in gray
3. **Header Bars**: Gray (#4A4A4A) with white text to separate sections
4. **Scenario Tables**: Low/Mid/High columns, color-coded headers
5. **Source Citations**: Always at bottom with footnotes

### 14 Slide Templates Identified

| Template | Use Case |
|----------|----------|
| Executive Summary | Opening slides, recommendations |
| Numbered Key Points | Investment highlights, thesis pillars |
| Peer Benchmarking | Valuation multiples, metrics |
| Comps Table | Trading comps with subject row highlighted |
| Time Series | Historical performance, multiple lines |
| Before/After | Value creation, renovations |
| Sources & Uses | Transaction structure, IPO analysis |
| Scenario Analysis | Disposition, strategic alternatives |
| Horizontal Bar + Pie | Rankings, geographic exposure |
| Gantt Chart | Transaction timeline, project phases |
| Heat Map | Performance matrix, annual returns |
| Portfolio Valuations | Fund investments, exit forecasts |
| Geographic Map | Property locations, market presence |
| Debt Benchmarking | Capital structure comparison |

### Color Palette (TD Securities Style)

- Primary (Subject): #00A651 (Green)
- Secondary: #006341 (Dark Green)
- Headers: #4A4A4A (Dark Gray)
- Negative: #C00000 (Red)
- Light Background: #F0F0F0

## Impact

1. Created comprehensive `docs/skills/SLIDE_DESIGN_GUIDE.md` (500+ lines)
2. Updated `ib_toolkit/pptx_generator.py` with new professional methods:
   - `add_peer_benchmarking_slide()`
   - `add_comps_table_slide()`
   - `add_sources_uses_slide()`
   - `add_numbered_highlights_slide()`
   - `add_before_after_slide()`
   - `_add_key_takeaway_bar()`
   - `_add_header_bar()`
   - `_add_source_citation()`

3. Updated `ir_toolkit/pptx_generator.py` with infrastructure-specific methods:
   - `add_performance_benchmarking_slide()`
   - `add_kpi_dashboard_slide()`
   - `add_waterfall_slide()`

4. Updated documentation references in:
   - `docs/skills/README.md`
   - `src/ii_skills/ib_toolkit/templates/case_study/SLIDE_REFERENCE.md`

## Future Improvements

- Add actual chart generation (currently using placeholder boxes)
- Add company logo insertion capability
- Add dashed red highlight box for forecast ranges
- Consider extracting more patterns from user's Historical Work
