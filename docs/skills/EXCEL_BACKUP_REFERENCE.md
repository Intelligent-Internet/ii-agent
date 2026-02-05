# Excel Backup Reference for Slide Templates

This document maps each PowerPoint slide template to its corresponding Excel backup structure. For templates that require underlying data, use these Excel structures to populate the slides.

---

## Template Files Location

**Path:** `src/ii_skills/shared/excel_templates/`

All 18 Excel template files with sample data and charts are available at the path above.

---

## Templates WITH Excel Backups Required (18 of 27)

| Template # | Name | Template File | Primary Data Type |
|------------|------|---------------|-------------------|
| 3 | Peer Benchmarking | [`03_peer_benchmarking.xlsx`](../../src/ii_skills/shared/excel_templates/03_peer_benchmarking.xlsx) | Bar chart data |
| 4 | Comps Table | [`04_comps_table.xlsx`](../../src/ii_skills/shared/excel_templates/04_comps_table.xlsx) | Trading comps matrix |
| 5 | Time Series | [`05_time_series.xlsx`](../../src/ii_skills/shared/excel_templates/05_time_series.xlsx) | Date + value series |
| 6 | Before/After | [`06_before_after.xlsx`](../../src/ii_skills/shared/excel_templates/06_before_after.xlsx) | KPI comparison |
| 7 | Sources & Uses | [`07_sources_uses.xlsx`](../../src/ii_skills/shared/excel_templates/07_sources_uses.xlsx) | Transaction structure |
| 8 | Scenario Analysis | [`08_scenario_analysis.xlsx`](../../src/ii_skills/shared/excel_templates/08_scenario_analysis.xlsx) | Low/Mid/High matrix |
| 9 | Horizontal Bar + Pie | [`09_horizontal_bar_pie.xlsx`](../../src/ii_skills/shared/excel_templates/09_horizontal_bar_pie.xlsx) | Rankings + categories |
| 10 | Gantt Chart | [`10_gantt_chart.xlsx`](../../src/ii_skills/shared/excel_templates/10_gantt_chart.xlsx) | Milestones + durations |
| 11 | Heat Map | [`11_heat_map.xlsx`](../../src/ii_skills/shared/excel_templates/11_heat_map.xlsx) | Performance matrix |
| 12 | Portfolio Valuations | [`12_portfolio_valuations.xlsx`](../../src/ii_skills/shared/excel_templates/12_portfolio_valuations.xlsx) | Investment returns |
| 14 | Debt Benchmarking | [`14_debt_benchmarking.xlsx`](../../src/ii_skills/shared/excel_templates/14_debt_benchmarking.xlsx) | Capital structure |
| 16 | 4-Quadrant Achievement | [`16_achievement_summary.xlsx`](../../src/ii_skills/shared/excel_templates/16_achievement_summary.xlsx) | KPI targets vs actuals |
| 17 | Track Record CAGR | [`17_track_record.xlsx`](../../src/ii_skills/shared/excel_templates/17_track_record.xlsx) | Historical metrics |
| 19 | Exit Strategy Grid | [`19_exit_summary.xlsx`](../../src/ii_skills/shared/excel_templates/19_exit_summary.xlsx) | Exit returns data |
| 22 | Debt Maturity Profile | [`22_debt_maturity.xlsx`](../../src/ii_skills/shared/excel_templates/22_debt_maturity.xlsx) | Debt schedule |
| 23 | Value Creation Bridge | [`23_value_bridge.xlsx`](../../src/ii_skills/shared/excel_templates/23_value_bridge.xlsx) | Waterfall components |
| 25 | Deal Showcase Grid | [`25_deal_showcase.xlsx`](../../src/ii_skills/shared/excel_templates/25_deal_showcase.xlsx) | Transaction metrics |
| 27 | Cost of Capital Spectrum | [`27_cost_of_capital.xlsx`](../../src/ii_skills/shared/excel_templates/27_cost_of_capital.xlsx) | Funding cost ranges |

---

## Templates WITHOUT Excel Backups (9 of 27)

| Template # | Name | Reason |
|------------|------|--------|
| 1 | Executive Summary | Narrative-driven, no data tables |
| 2 | Numbered Key Points | Primarily text with optional charts |
| 13 | Geographic Map | Visual/location-based, manual markers |
| 15 | Mission Statement | Pure narrative |
| 18 | 3-Pillar Strategy Flow | Conceptual diagram |
| 20 | Investment Checklist | Text criteria (optional scoring) |
| 21 | Macro Themes Grid | Conceptual themes |
| 24 | Platform Overview | Mixed (simple metrics can be hard-coded) |
| 26 | Investment Perimeter | Conceptual evolution diagram |

---

## Excel Backup Structures

### Template 3: Peer Benchmarking Bar Chart

**Sheet Name:** `Peer_Benchmarking`

| Column | Header | Format | Example |
|--------|--------|--------|---------|
| A | Company | Text | "Peer A" |
| B | Logo_Path | Text (optional) | "logos/peer_a.png" |
| C | Metric_Value | Number | 23.8 |
| D | Is_Subject | Boolean | FALSE |

**Chart Output:** Horizontal bar chart sorted by Metric_Value descending, subject company in green.

```
Sample Data:
Company         Logo_Path           Metric_Value    Is_Subject
Peer A          logos/peer_a.png    23.8            FALSE
Peer B          logos/peer_b.png    22.4            FALSE
Subject Company logos/subject.png   18.2            TRUE
Peer C          logos/peer_c.png    16.7            FALSE
```

---

### Template 4: Comprehensive Comps Table

**Sheet Name:** `Trading_Comps`

| Column | Header | Format | Example |
|--------|--------|--------|---------|
| A | Company | Text | "Peer A" |
| B | Ticker | Text | "PEER.TO" |
| C | Price | Currency | $45.50 |
| D | Mkt_Cap_M | Number | 2,450 |
| E | EV_M | Number | 3,100 |
| F | PE_CY | Number | 18.5 |
| G | PE_NY | Number | 16.2 |
| H | EV_EBITDA_CY | Number | 12.3 |
| I | EV_EBITDA_NY | Number | 11.1 |
| J | Is_Subject | Boolean | FALSE |

**Additional Row:** "Average" or "Median" row with calculated values.

```
Sample Data:
Company    Ticker    Price    Mkt_Cap    EV      PE_CY   PE_NY   EV_EBITDA_CY   EV_EBITDA_NY   Is_Subject
Peer A     PEER.TO   $45.50   2,450      3,100   18.5x   16.2x   12.3x          11.1x          FALSE
Peer B     PB.TO     $32.25   1,890      2,350   21.2x   18.7x   14.1x          12.8x          FALSE
Subject    SUBJ.TO   $28.00   1,450      1,850   15.8x   14.1x   10.5x          9.8x           TRUE
Average    -         -        -          -       18.5x   16.3x   12.3x          11.2x          -
```

---

### Template 5: Time Series Line Chart

**Sheet Name:** `Time_Series`

| Column | Header | Format | Example |
|--------|--------|--------|---------|
| A | Date | Date | 2024-01-15 |
| B | Subject_Value | Number | 105.2 |
| C | Benchmark_1 | Number | 102.8 |
| D | Benchmark_2 | Number (optional) | 101.5 |

**Chart Output:** Line chart with Date on x-axis, multiple series plotted. Subject line in green (thicker), benchmarks in gray.

```
Sample Data:
Date         Subject_Value    Benchmark_1    Benchmark_2
2024-01-15   100.0            100.0          100.0
2024-02-15   105.2            102.8          101.5
2024-03-15   108.7            104.2          103.8
2024-04-15   112.3            107.5          106.2
...
```

**Summary Table (optional):**
| Metric | Subject | Benchmark_1 | Benchmark_2 |
|--------|---------|-------------|-------------|
| Cumulative Return | +45.2% | +32.1% | +28.5% |
| CAGR | 12.5% | 9.2% | 8.3% |

---

### Template 6: Before/After Comparison

**Sheet Name:** `Before_After`

| Column | Header | Format | Example |
|--------|--------|--------|---------|
| A | Metric | Text | "Revenue" |
| B | Before_Value | Number/Currency | $2,780 |
| C | After_Value | Number/Currency | $5,087 |
| D | Change_Pct | Percent | 83% |
| E | Change_Abs | Number/Currency | $2,307 |

**KPI Summary Section:**
| KPI | Value |
|-----|-------|
| Cost | $5,000 |
| Uplift | +$400/month |
| Payback | 1 Year |
| ROI | 96% |

```
Sample Data:
Metric          Before      After       Change_Pct    Change_Abs
Revenue         $2,780      $5,087      83%           $2,307
Rent/Unit       $2,780      $3,395      22%           $615
Care Revenue    $0          $1,692      n/a           $1,692
Occupancy       85%         94%         11%           9%
```

---

### Template 7: Sources & Uses / Transaction Summary

**Sheet Name:** `Sources_Uses`

**Sources Table:**
| Column | Header | Format |
|--------|--------|--------|
| A | Source_Item | Text |
| B | Low_Case | Number |
| C | Mid_Case | Number |
| D | High_Case | Number |

**Uses Table:**
| Column | Header | Format |
|--------|--------|--------|
| A | Use_Item | Text |
| B | Low_Case | Number |
| C | Mid_Case | Number |
| D | High_Case | Number |

**Valuation Summary:**
| Metric | Low | Mid | High |
|--------|-----|-----|------|
| AFFO | $22.0 | $22.0 | $22.0 |
| Multiple | 13.5x | 14.5x | 15.5x |
| Equity Value | $297 | $319 | $341 |
| + Net Debt | $234 | $234 | $234 |
| = Enterprise Value | $502 | $521 | $541 |

```
Sample Sources:
Source_Item         Low     Mid     High
Equity Issue        $125    $138    $150
Retained Interest   $142    $150    $157
Portfolio Debt      $282    $282    $282
Total Sources       $549    $569    $589

Sample Uses:
Use_Item            Low     Mid     High
Purchase Price      $488    $507    $526
Transaction Costs   $14     $14     $15
Debt Repayment      $47     $47     $47
Total Uses          $549    $569    $589
```

---

### Template 8: Scenario Analysis

**Sheet Name:** `Scenario_Analysis`

**Assumptions Matrix:**
| Column | Header | Format |
|--------|--------|--------|
| A | Assumption | Text |
| B | Bear_Case | Number |
| C | Base_Case | Number |
| D | Bull_Case | Number |

**Outputs Matrix:**
| Column | Header | Format |
|--------|--------|--------|
| A | Output_Metric | Text |
| B | Bear_Case | Number |
| C | Base_Case | Number |
| D | Bull_Case | Number |

```
Sample Assumptions:
Assumption          Bear        Base        Bull
Revenue Growth      2.0%        5.0%        8.0%
EBITDA Margin       18.0%       22.0%       25.0%
Exit Multiple       8.0x        10.0x       12.0x
Debt Paydown        50%         75%         100%

Sample Outputs:
Output_Metric       Bear        Base        Bull
Exit EV             $850        $1,200      $1,650
Equity Value        $520        $780        $1,150
IRR                 12.5%       18.5%       24.0%
MOIC                1.8x        2.4x        3.2x
```

---

### Template 9: Horizontal Bar Chart + Pie

**Sheet Name:** `Rankings`

**Bar Chart Data:**
| Column | Header | Format |
|--------|--------|--------|
| A | Category | Text |
| B | Value | Number |
| C | Annotation | Text (optional) |
| D | Is_Subject | Boolean |

**Pie Chart Data:**
| Column | Header | Format |
|--------|--------|--------|
| A | Segment | Text |
| B | Percentage | Percent |

```
Sample Bar Data:
Category        Value       Annotation          Is_Subject
City A          23.7%       #1 in Region        FALSE
City B          21.3%       -                   FALSE
City C          19.5%       -                   TRUE
City D          18.3%       #1 in Province      FALSE

Sample Pie Data:
Segment         Percentage
Top Markets     15%
Other Markets   85%
```

---

### Template 10: Gantt Chart / Timeline

**Sheet Name:** `Timeline`

| Column | Header | Format |
|--------|--------|--------|
| A | Workstream | Text |
| B | Start_Date | Date |
| C | End_Date | Date |
| D | Duration_Weeks | Number |
| E | Is_Milestone | Boolean |

**Milestone Markers:**
| Column | Header | Format |
|--------|--------|--------|
| A | Milestone_Name | Text |
| B | Target_Date | Date |
| C | Description | Text |

```
Sample Data:
Workstream      Start_Date    End_Date      Duration    Is_Milestone
Planning        2025-01-01    2025-03-31    13          FALSE
Appraisals      2025-01-15    2025-06-30    24          FALSE
Due Diligence   2025-04-01    2025-09-30    26          FALSE
Filing          2025-10-01    2025-11-30    9           FALSE
Launch          2025-12-01    2025-12-01    0           TRUE

Milestones:
Milestone_Name      Target_Date     Description
Board Approval      2025-03-15      Internal approval
Prospectus Filed    2025-10-15      Regulatory filing
IPO Launch          2025-12-01      Market debut
```

---

### Template 11: Heat Map / Performance Matrix

**Sheet Name:** `Heat_Map`

| Column | Header | Format |
|--------|--------|--------|
| A | Row_Label | Text |
| B-F | Year columns | Number |
| G | Average/IRR | Number |

**Color Scale Rules:**
- Dark Green: > 20%
- Green: 10% - 20%
- Light Green: 0% - 10%
- Red: < 0%

```
Sample Data:
Strategy        2020    2021    2022    2023    2024    5-Yr IRR
Strategy A      17.1%   21.3%   31.4%   13.0%   12.4%   15.8%
Strategy B      14.9%   18.8%   20.3%   12.5%   10.8%   15.4%
Strategy C      7.1%    (2.8%)  12.1%   8.0%    (8.2%)  7.9%
```

---

### Template 12: Portfolio Valuations Table

**Sheet Name:** `Portfolio_Valuations`

| Column | Header | Format |
|--------|--------|--------|
| A | Company | Text |
| B | Logo_Path | Text |
| C | Invested_Amount | Currency |
| D | Current_MOIC | Number |
| E | Current_IRR | Percent |
| F | Exit_Date | Text |
| G | Exit_MOIC_Low | Number |
| H | Exit_MOIC_High | Number |
| I | Exit_IRR_Low | Percent |
| J | Exit_IRR_High | Percent |

```
Sample Data:
Company     Logo_Path       Invested    Current_MOIC    Current_IRR    Exit_Date    Exit_MOIC_Low    Exit_MOIC_High    Exit_IRR_Low    Exit_IRR_High
Company A   logos/a.png     $28.6M      2.00x           39.7%          H1'27        2.5x             3.0x              28%             34%
Company B   logos/b.png     $27.2M      1.60x           87.5%          2028         2.5x             3.0x              26%             32%
Company C   logos/c.png     $42.1M      1.85x           25.3%          H2'26        2.2x             2.8x              22%             28%
```

---

### Template 14: Debt Structure Benchmarking

**Sheet Name:** `Debt_Benchmarking`

| Column | Header | Format |
|--------|--------|--------|
| A | Debt_Type | Text |
| B | Company_A_Value | Number |
| C | Company_A_Pct | Percent |
| D | Company_B_Value | Number |
| E | Company_B_Pct | Percent |
| F | Subject_Value | Number |
| G | Subject_Pct | Percent |

```
Sample Data:
Debt_Type           Company_A    %_A     Company_B    %_B     Subject    %_Subj
CMHC Insured        $1,631       49.6%   $598         47.1%   $30        12.7%
Non-CMHC Insured    $358         10.9%   $189         14.9%   $205       87.3%
Unsecured Debt      $950         28.9%   $450         35.4%   -          -
Term Loan           $149         4.5%    -            -       -          -
Credit Facility     $190         5.8%    $30          2.4%    -          -
Total Debt          $3,286       100%    $1,270       100%    $234       100%
Credit Capacity     $400         12.2%   $309         24.3%   $65        27.7%
Undrawn Capacity    $210         6.4%    $309         24.3%   $65        27.7%
```

---

### Template 16: 4-Quadrant Achievement Summary

**Sheet Name:** `Achievement_Summary`

| Column | Header | Format |
|--------|--------|--------|
| A | Quadrant | Integer (1-4) |
| B | Title | Text |
| C | Subtitle | Text |
| D | Target | Number/Text |
| E | Actual | Number/Text |
| F | Status | Text (Achieved/In Progress/Behind) |

```
Sample Data:
Quadrant    Title                   Subtitle            Target      Actual      Status
1           Executed strategic      priorities          4           4           Achieved
2           Delivered record        financial results   $3.20 FFO   $3.32 FFO   Achieved
3           Maintained strong       balance sheet       BBB+        BBB+        Achieved
4           Advanced ESG            priorities          3 goals     3 goals     Achieved
```

---

### Template 17: Track Record CAGR Line Chart

**Sheet Name:** `Track_Record`

| Column | Header | Format |
|--------|--------|--------|
| A | Year | Integer |
| B | Metric_Value | Number |
| C | Distribution | Number (optional) |

**Summary Metrics:**
| Metric | Value |
|--------|-------|
| Start Value | $0.42 |
| End Value | $3.32 |
| CAGR | 14% |
| Period | 2009-2025 |

```
Sample Data:
Year    FFO_Per_Unit    Distribution
2009    $0.42           $0.38
2010    $0.51           $0.45
2011    $0.62           $0.52
...
2024    $3.15           $2.10
2025    $3.32           $2.20
```

---

### Template 19: Exit Strategy Summary Grid

**Sheet Name:** `Exit_Summary`

| Column | Header | Format |
|--------|--------|--------|
| A | Transaction_Name | Text |
| B | Logo_Path | Text |
| C | Exit_Strategy | Text |
| D | Proceeds_M | Number |
| E | IRR | Percent |
| F | MoC | Number |

```
Sample Data:
Transaction     Logo_Path       Exit_Strategy       Proceeds    IRR     MoC
Deal A          logos/a.png     Full exit           $480M       17%     3.6x
Deal B          logos/b.png     Partial sale        $430M       19%     7.5x
Deal C          logos/c.png     Partial sale        $390M       18%     2.9x
Deal D          logos/d.png     Staged exit         $580M       22%     3.8x
Deal E          logos/e.png     Public market       $620M       25%     1.6x
TOTAL           -               Various             ~$2.8B      ~20%    4.0x
```

---

### Template 22: Debt Maturity Profile

**Sheet Name:** `Debt_Maturity`

| Column | Header | Format |
|--------|--------|--------|
| A | Year | Integer |
| B | Amount_B | Number |
| C | Facility_Type | Text |
| D | Rate | Percent |

**Summary Metrics:**
| Metric | Value |
|--------|-------|
| Outstanding | ~$4.2 billion |
| Average Rate | 5.0% |
| Average Term | 14 Years |

```
Sample Data:
Year        Amount      Facility_Type           Rate
2026        $0.3B       Corporate bonds         4.5%
2027        $0.5B       Term loan               5.2%
2028        $0.5B       Revolving credit        SOFR+150
2029        $0.4B       Project finance         4.8%
2030+       $2.5B       Long-dated bonds        5.0%
```

---

### Template 23: Value Creation Bridge / Waterfall

**Sheet Name:** `Value_Bridge`

| Column | Header | Format |
|--------|--------|--------|
| A | Component | Text |
| B | Value_Low | Number |
| C | Value_High | Number |
| D | Is_Subtotal | Boolean |

**Bridge Components:**
```
Sample Data:
Component               Value_Low   Value_High  Is_Subtotal
Inflation Pass-through  3%          4%          FALSE
GDP Growth              1%          2%          FALSE
Reinvested Capital      2%          3%          FALSE
= Organic Growth        6%          9%          TRUE
```

---

### Template 25: Deal Showcase Grid

**Sheet Name:** `Deal_Showcase`

| Column | Header | Format |
|--------|--------|--------|
| A | Deal_Name | Text |
| B | Logo_Path | Text |
| C | Sector | Text |
| D | Deal_Type | Text |
| E | Enterprise_Value | Currency |
| F | Close_Date | Text |

```
Sample Data:
Deal_Name       Logo_Path       Sector      Deal_Type       EV          Close_Date
Deal A          logos/a.png     Midstream   Value-based     $9.1B       Jul 2025
Deal B          logos/b.png     Data        Platform        $6.9B       Sep 2025
Deal C          logos/c.png     Transport   Partnership     $5.3B       Q1 2026
Deal D          logos/d.png     Utilities   Carve-out       $1.0B       Q4 2025
```

---

### Template 27: Cost of Capital Spectrum

**Sheet Name:** `Cost_of_Capital`

| Column | Header | Format |
|--------|--------|--------|
| A | Funding_Source | Text |
| B | Cost_Low | Percent |
| C | Cost_High | Percent |
| D | Constraints | Text |
| E | Position | Integer (1=lowest cost) |

```
Sample Data:
Funding_Source      Cost_Low    Cost_High   Constraints             Position
Corporate Debt      3.5%        4.5%        BBB+ rating limit       1
Preferred Equity    5.5%        6.5%        -                       2
Asset Sales         9.0%        11.0%       Target range            3
Common Equity       12.0%       15.0%       Dilution concerns       4
```

---

## Implementation Notes

### Excel Generation Code Location

Add Excel backup generators to:
- **IB Toolkit:** `src/ii_skills/ib_toolkit/templates/excel_models/backup_generators.py`
- **IR Toolkit:** `src/ii_skills/ir_toolkit/excel_generators/backup_generators.py`

### Python Template

```python
import openpyxl
from openpyxl.chart import LineChart, BarChart, PieChart, Reference
from openpyxl.utils.dataframe import dataframe_to_rows

def generate_time_series_backup(
    data: list[dict],
    output_path: str,
    subject_name: str = "Subject",
    metric_name: str = "Value"
):
    """
    Generate Excel backup for Time Series slide.

    Args:
        data: List of dicts with 'date', 'subject_value', 'benchmark_1', etc.
        output_path: Path to save Excel file
        subject_name: Name of subject for chart legend
        metric_name: Y-axis label
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Time_Series"

    # Headers
    ws['A1'] = "Date"
    ws['B1'] = subject_name
    ws['C1'] = "Benchmark"

    # Data
    for i, row in enumerate(data, start=2):
        ws[f'A{i}'] = row['date']
        ws[f'B{i}'] = row['subject_value']
        ws[f'C{i}'] = row.get('benchmark_1', None)

    # Create chart
    chart = LineChart()
    chart.title = f"{metric_name} Over Time"
    chart.y_axis.title = metric_name
    chart.x_axis.title = "Date"

    data_ref = Reference(ws, min_col=2, max_col=3, min_row=1, max_row=len(data)+1)
    cats_ref = Reference(ws, min_col=1, min_row=2, max_row=len(data)+1)

    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)

    # Style: Subject in green
    chart.series[0].graphicalProperties.line.solidFill = "00A651"

    ws.add_chart(chart, "E2")

    wb.save(output_path)
```

### Usage Pattern

```python
# Example: Generate backup for a comps slide
from backup_generators import generate_comps_backup

comps_data = [
    {"company": "Peer A", "ticker": "PA.TO", "price": 45.50, "pe_cy": 18.5, "is_subject": False},
    {"company": "Subject", "ticker": "SUBJ.TO", "price": 28.00, "pe_cy": 15.8, "is_subject": True},
    # ...
]

generate_comps_backup(
    data=comps_data,
    output_path="C:/Users/user/Downloads/comps_backup.xlsx"
)
```

---

## File Naming Convention

```
{company_name}_{template_type}_{date}.xlsx

Examples:
- Target_Corp_trading_comps_2025-02-04.xlsx
- Fund_V_portfolio_valuations_2025-02-04.xlsx
- Project_Alpha_scenario_analysis_2025-02-04.xlsx
```

---

*Last Updated: 2026-02-04*
