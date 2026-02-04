# IB Toolkit Module Reference Index

This directory contains reference templates for all available PE/IB analysis modules. Each module has both an Excel model and PowerPoint slides that can be generated together or independently.

## Template File Naming Convention
- `[Module]_Template.xlsx` - Excel financial model
- `[Module]_Template.pptx` - PowerPoint slides

## How to Create a New Module

When creating a new module similar to an existing one:

1. **Review the reference template** - Open both .xlsx and .pptx to understand the structure
2. **Copy the Excel method** from `excel_modules.py` as a starting point
3. **Copy the Slide method** from `slide_modules.py` as a starting point
4. **Add to SLIDE_MODULES registry** in `slide_modules.py`
5. **Add quick access function** at the bottom of `slide_modules.py`
6. **Update QUICK_REFERENCE.md** with the new module mapping

---

## Transaction Structure Modules

### Add-on / Bolt-on Analysis
| File | Description |
|------|-------------|
| `Addon_Analysis_Template.xlsx` | Platform + add-on combination metrics, combined financials, accretion analysis |
| `Addon_Analysis_Template.pptx` | 4 slides: Overview, Combined Financials, Returns Accretion |

**Excel Method:** `add_addon_analysis()`
**Slide Method:** `add_addon_analysis_slides()`
**Quick Function:** `generate_addon_slides(company, path)`

**Use When:** Analyzing a bolt-on acquisition to an existing platform investment

---

### Synergy Model
| File | Description |
|------|-------------|
| `Synergy_Model_Template.xlsx` | Revenue and cost synergies, one-time costs, realization timeline |
| `Synergy_Model_Template.pptx` | 4 slides: Summary, Detail & Assumptions, Timeline |

**Excel Method:** `add_synergy_model()`
**Slide Method:** `add_synergy_slides()`
**Quick Function:** `generate_synergy_slides(company, path)`

**Use When:** Quantifying synergies for M&A transactions

---

### Carve-out Analysis
| File | Description |
|------|-------------|
| `Carveout_Analysis_Template.xlsx` | Standalone adjustments, stranded costs, TSA requirements |
| `Carveout_Analysis_Template.pptx` | 4 slides: Overview, Standalone Adjustments, Separation Timeline |

**Excel Method:** `add_carveout_analysis()`
**Slide Method:** `add_carveout_slides()`
**Quick Function:** `generate_carveout_slides(company, path)`

**Use When:** Acquiring a division/business unit from a larger parent

---

### Earnout / Contingent Consideration
| File | Description |
|------|-------------|
| `Earnout_Model_Template.xlsx` | Performance milestones, probability-weighted valuation |
| `Earnout_Model_Template.pptx` | 3 slides: Structure, Valuation & Risk Assessment |

**Excel Method:** `add_earnout_model()`
**Slide Method:** `add_earnout_slides()`
**Quick Function:** `generate_earnout_slides(company, path)`

**Use When:** Structuring contingent consideration in purchase agreements

---

### Purchase Price Allocation (PPA)
| File | Description |
|------|-------------|
| `PPA_Template.xlsx` | Asset step-up, identified intangibles, goodwill calculation |
| `PPA_Template.pptx` | 3 slides: PPA Summary, Intangibles Detail |

**Excel Method:** `add_purchase_price_allocation()`
**Slide Method:** `add_ppa_slides()`
**Quick Function:** `generate_ppa_slides(company, path)`

**Use When:** Allocating purchase price to acquired assets for accounting

---

## Value Creation Modules

### Value Creation Bridge
| File | Description |
|------|-------------|
| `Value_Creation_Template.xlsx` | EBITDA growth, multiple expansion, deleveraging attribution |
| `Value_Creation_Template.pptx` | 3 slides: Value Bridge, Value Drivers |

**Excel Method:** `add_value_creation_bridge()`
**Slide Method:** `add_value_creation_slides()`
**Quick Function:** `generate_value_creation_slides(company, path)`

**Use When:** Attributing equity value creation to key drivers

---

### 100-Day Plan
| File | Description |
|------|-------------|
| `Hundred_Day_Plan_Template.xlsx` | Post-close priorities, initiative matrix, milestone timeline |
| `Hundred_Day_Plan_Template.pptx` | 4 slides: Overview, Priority Matrix, Milestone Timeline |

**Excel Method:** `add_hundred_day_plan()`
**Slide Method:** `add_hundred_day_slides()`
**Quick Function:** `generate_hundred_day_slides(company, path)`

**Use When:** Planning post-acquisition value creation initiatives

---

### Exit Readiness Assessment
| File | Description |
|------|-------------|
| `Exit_Readiness_Template.xlsx` | Exit options analysis, readiness scorecard |
| `Exit_Readiness_Template.pptx` | 3 slides: Exit Options, Readiness Scorecard |

**Excel Method:** `add_exit_readiness()`
**Slide Method:** `add_exit_readiness_slides()`
**Quick Function:** `generate_exit_readiness_slides(company, path)`

**Use When:** Assessing portfolio company exit timing and preparation

---

### Management Incentive Plan (MIP)
| File | Description |
|------|-------------|
| `MIP_Template.xlsx` | Pool allocation, vesting terms, payout scenarios |
| `MIP_Template.pptx` | 3 slides: Structure Overview, Payout Scenarios |

**Excel Method:** `add_management_incentive_plan()`
**Slide Method:** `add_mip_slides()`
**Quick Function:** `generate_mip_slides(company, path)`

**Use When:** Designing management equity incentive structures

---

## Specialized Modules

### Rollup / Platform Build Model
| File | Description |
|------|-------------|
| `Rollup_Model_Template.xlsx` | Multi-acquisition tracking, combined metrics, pipeline |
| `Rollup_Model_Template.pptx` | 4 slides: Summary, Strategy & Pipeline, Combined Metrics |

**Excel Method:** `add_rollup_model()`
**Slide Method:** `add_rollup_slides()`
**Quick Function:** `generate_rollup_slides(company, path)`

**Use When:** Executing a buy-and-build / consolidation strategy

---

### Tax Analysis
| File | Description |
|------|-------------|
| `Tax_Analysis_Template.xlsx` | Tax structure, NOLs, step-up value, shield analysis |
| `Tax_Analysis_Template.pptx` | 3 slides: Structure Overview, Tax Shield Value |

**Excel Method:** `add_tax_analysis()`
**Slide Method:** `add_tax_slides()`
**Quick Function:** `generate_tax_analysis_slides(company, path)`

**Use When:** Analyzing tax implications and asset step-up value

---

### Control Premium Analysis
| File | Description |
|------|-------------|
| `Control_Premium_Template.xlsx` | Premium to unaffected, precedent transaction premiums |
| `Control_Premium_Template.pptx` | 3 slides: Premium Analysis, Precedent Premiums |

**Excel Method:** `add_control_premium_analysis()`
**Slide Method:** `add_control_premium_slides()`
**Quick Function:** `generate_control_premium_slides(company, path)`

**Use When:** Analyzing takeover premiums for public company acquisitions

---

## Existing Core Templates

These institutional templates were created previously:

| Template | Sheets/Slides | Description |
|----------|---------------|-------------|
| `Institutional_LBO_Template.xlsx` | 17 sheets | Comprehensive LBO model with all core modules |
| `Institutional_Deck_Template.pptx` | 60+ slides | Full investment memo deck |

---

## Code File Locations

| File | Purpose |
|------|---------|
| `templates/excel_models/excel_modules.py` | All Excel model generation code |
| `templates/case_study/slide_modules.py` | All PowerPoint slide generation code |
| `QUICK_REFERENCE.md` | User request to module mapping |
| `templates/reference_outputs/MODULE_INDEX.md` | This file |

---

## Creating a New Module Checklist

- [ ] Define the analysis type and key outputs
- [ ] Create Excel method in `excel_modules.py`
- [ ] Create Slide method in `slide_modules.py`
- [ ] Add entry to `SLIDE_MODULES` registry
- [ ] Add quick access function
- [ ] Update `QUICK_REFERENCE.md`
- [ ] Generate reference template to `reference_outputs/`
- [ ] Update this `MODULE_INDEX.md`
- [ ] Test both Excel and Slide generation
- [ ] Commit and push to GitHub
