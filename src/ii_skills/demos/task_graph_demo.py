"""
Task Graph Demo: Case Study Critique

Demonstrates the reusable task graph utility by:
1. Reading a case study
2. Analyzing different sections in parallel
3. Generating a PowerPoint critique slide

Usage:
    python -m ii_skills.demos.task_graph_demo
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ii_skills.shared.task_graph import (
    TaskGraph,
    Task,
    TaskGraphExecutor,
    LoggingCallbacks,
    ExecutionBudget,
)
from ii_skills.shared.event_telemetry import TelemetryLogger
from ii_skills.shared.run_budgets import get_budget_profile, BudgetProfile


# ============================================================================
# CASE STUDY DATA (extracted from PDF)
# ============================================================================

CASE_STUDY_DATA = {
    "title": "Optical Distributor Group Analysis",
    "date": "January 26, 2026",
    "company": "ODG (Optical Distributor Group)",
    "pages": {
        1: {
            "title": "Cover Page",
            "content": "VENTURE & GROWTH | OPTICAL DISTRIBUTOR GROUP ANALYSIS",
            "issues": ["Header says 'VENTURE & GROWTH' but this is an LBO/buyout transaction"]
        },
        2: {
            "title": "Company Overview",
            "content": "ODG is #2 U.S. Optical Distributor with industry-leading metrics",
            "issues": []
        },
        3: {
            "title": "Projections",
            "content": "8% Revenue CAGR with Margin Stability",
            "issues": [
                "Page contains 'NTD' placeholders - incomplete",
                "Shows 'Combo chart + table' placeholder instead of actual content",
                "Assessment of cash flows section not completed"
            ]
        },
        4: {
            "title": "Investment Recommendation",
            "content": "Qualified Buy recommendation",
            "issues": [
                "CRITICAL: Content is from WRONG case study - mentions QuickBooks, AI accounting, SaaS",
                "References 'Sasha' founder - not relevant to ODG",
                "Mentions Series C at $856M valuation - ODG is a buyout, not VC",
                "Mentions 136% net dollar retention, 66% ARR growth - SaaS metrics, not distributor",
                "This entire page appears copy-pasted from a different analysis"
            ]
        },
        5: {
            "title": "Key Risks",
            "content": "Risk matrix with 5 key risks identified",
            "issues": []
        },
        6: {
            "title": "Valuation Benchmarking",
            "content": "Comparable companies and precedent transactions",
            "issues": []
        },
        7: {
            "title": "Valuation Analysis",
            "content": "$215M entry valuation analysis",
            "issues": []
        },
        8: {
            "title": "Transaction Return Profile",
            "content": "Scenario analysis and sensitivity tables",
            "issues": []
        },
        9: {
            "title": "Due Diligence Approach",
            "content": "Structured DD plan",
            "issues": []
        }
    }
}


# ============================================================================
# TASK HANDLERS
# ============================================================================

async def analyze_structure(context: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze overall case structure."""
    data = context["case_data"]

    return {
        "total_pages": len(data["pages"]),
        "sections": [p["title"] for p in data["pages"].values()],
        "has_cover": True,
        "has_recommendation": True,
        "has_risks": True,
        "has_valuation": True,
        "has_returns": True,
        "has_dd_plan": True,
    }


async def analyze_content_quality(context: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze content quality across pages."""
    data = context["case_data"]

    pages_with_issues = []
    all_issues = []

    for page_num, page in data["pages"].items():
        if page["issues"]:
            pages_with_issues.append(page_num)
            for issue in page["issues"]:
                all_issues.append({
                    "page": page_num,
                    "section": page["title"],
                    "issue": issue,
                    "severity": "CRITICAL" if "CRITICAL" in issue else "WARNING"
                })

    return {
        "pages_with_issues": pages_with_issues,
        "total_issues": len(all_issues),
        "critical_issues": sum(1 for i in all_issues if i["severity"] == "CRITICAL"),
        "issues": all_issues,
    }


async def analyze_consistency(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check for consistency issues."""
    data = context["case_data"]

    inconsistencies = []

    # Check header vs content mismatch
    cover = data["pages"][1]
    if "VENTURE & GROWTH" in cover["content"]:
        inconsistencies.append({
            "type": "header_mismatch",
            "description": "Cover says 'Venture & Growth' but transaction is an LBO buyout",
            "severity": "WARNING"
        })

    # Check for placeholder content
    for page_num, page in data["pages"].items():
        if any("NTD" in issue or "placeholder" in issue.lower() for issue in page["issues"]):
            inconsistencies.append({
                "type": "incomplete_content",
                "page": page_num,
                "description": f"Page {page_num} ({page['title']}) has placeholder content",
                "severity": "WARNING"
            })

    # Check for wrong case content
    page4 = data["pages"][4]
    if any("WRONG" in issue or "copy-paste" in issue.lower() for issue in page4["issues"]):
        inconsistencies.append({
            "type": "wrong_content",
            "page": 4,
            "description": "Investment Recommendation page contains content from different case study",
            "severity": "CRITICAL"
        })

    return {
        "inconsistencies": inconsistencies,
        "total_inconsistencies": len(inconsistencies),
        "critical_count": sum(1 for i in inconsistencies if i["severity"] == "CRITICAL"),
    }


async def generate_critique_summary(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate final critique summary from all analyses."""
    structure = context.get("structure_result", {})
    quality = context.get("quality_result", {})
    consistency = context.get("consistency_result", {})

    # Overall grade
    critical_count = quality.get("critical_issues", 0) + consistency.get("critical_count", 0)
    warning_count = quality.get("total_issues", 0) - quality.get("critical_issues", 0)

    if critical_count > 0:
        grade = "NEEDS REVISION"
        grade_color = "red"
    elif warning_count > 2:
        grade = "ACCEPTABLE WITH FIXES"
        grade_color = "yellow"
    else:
        grade = "GOOD"
        grade_color = "green"

    return {
        "grade": grade,
        "grade_color": grade_color,
        "critical_issues": critical_count,
        "warnings": warning_count,
        "top_issues": [
            "Page 4: Investment recommendation is from a DIFFERENT case study (SaaS/AI accounting vs. Optical Distribution)",
            "Page 3: Projections page incomplete with 'NTD' placeholders",
            "Cover: Header says 'Venture & Growth' but this is an LBO transaction",
        ],
        "strengths": [
            "Comprehensive risk analysis with probability/impact matrix",
            "Solid valuation benchmarking with comps and precedents",
            "Detailed return sensitivity analysis",
            "Thorough due diligence framework",
        ],
    }


async def generate_powerpoint(context: Dict[str, Any]) -> str:
    """Generate the PowerPoint critique slide."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RgbColor
    from pptx.enum.text import PP_ALIGN

    summary = context.get("summary_result", {})
    output_path = context.get("output_path", "case_critique.pptx")

    # Create presentation
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Add slide
    blank_layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(blank_layout)

    # Title
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.6))
    title_frame = title_box.text_frame
    title_para = title_frame.paragraphs[0]
    title_para.text = "Case Study Critique: ODG Analysis (v1)"
    title_para.font.size = Pt(28)
    title_para.font.bold = True
    title_para.font.color.rgb = RgbColor(0, 51, 102)

    # Subtitle with grade
    subtitle_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.9), Inches(12), Inches(0.4))
    subtitle_frame = subtitle_box.text_frame
    subtitle_para = subtitle_frame.paragraphs[0]
    grade = summary.get("grade", "NEEDS REVISION")
    subtitle_para.text = f"Overall Assessment: {grade}"
    subtitle_para.font.size = Pt(18)
    subtitle_para.font.bold = True
    if grade == "NEEDS REVISION":
        subtitle_para.font.color.rgb = RgbColor(192, 0, 0)
    elif grade == "ACCEPTABLE WITH FIXES":
        subtitle_para.font.color.rgb = RgbColor(192, 192, 0)
    else:
        subtitle_para.font.color.rgb = RgbColor(0, 128, 0)

    # Critical Issues Section (Left)
    issues_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(6), Inches(2.5))
    issues_frame = issues_box.text_frame
    issues_frame.word_wrap = True

    # Issues header
    issues_header = issues_frame.paragraphs[0]
    issues_header.text = "Critical Issues"
    issues_header.font.size = Pt(16)
    issues_header.font.bold = True
    issues_header.font.color.rgb = RgbColor(192, 0, 0)

    # Issue items
    for issue in summary.get("top_issues", []):
        p = issues_frame.add_paragraph()
        p.text = f"• {issue}"
        p.font.size = Pt(11)
        p.space_before = Pt(6)

    # Strengths Section (Right)
    strengths_box = slide.shapes.add_textbox(Inches(6.8), Inches(1.5), Inches(6), Inches(2.5))
    strengths_frame = strengths_box.text_frame
    strengths_frame.word_wrap = True

    # Strengths header
    strengths_header = strengths_frame.paragraphs[0]
    strengths_header.text = "Strengths"
    strengths_header.font.size = Pt(16)
    strengths_header.font.bold = True
    strengths_header.font.color.rgb = RgbColor(0, 128, 0)

    # Strength items
    for strength in summary.get("strengths", []):
        p = strengths_frame.add_paragraph()
        p.text = f"• {strength}"
        p.font.size = Pt(11)
        p.space_before = Pt(6)

    # Recommendations Section (Bottom)
    rec_box = slide.shapes.add_textbox(Inches(0.5), Inches(4.2), Inches(12), Inches(2.5))
    rec_frame = rec_box.text_frame
    rec_frame.word_wrap = True

    rec_header = rec_frame.paragraphs[0]
    rec_header.text = "Recommended Actions Before Final Submission"
    rec_header.font.size = Pt(16)
    rec_header.font.bold = True
    rec_header.font.color.rgb = RgbColor(0, 51, 102)

    recommendations = [
        "1. URGENT: Replace Page 4 content entirely - currently shows AI/SaaS case instead of ODG optical distribution",
        "2. Complete Page 3 projections - remove 'NTD' placeholders and add actual financial projections chart",
        "3. Update cover header from 'Venture & Growth' to 'Private Equity' or 'Buyout' to match deal type",
        "4. Add explicit investment recommendation for ODG with thesis points specific to optical distribution",
    ]

    for rec in recommendations:
        p = rec_frame.add_paragraph()
        p.text = rec
        p.font.size = Pt(11)
        p.space_before = Pt(6)

    # Footer
    footer_box = slide.shapes.add_textbox(Inches(0.5), Inches(7.0), Inches(12), Inches(0.3))
    footer_frame = footer_box.text_frame
    footer_para = footer_frame.paragraphs[0]
    footer_para.text = f"Generated by Task Graph Demo | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    footer_para.font.size = Pt(9)
    footer_para.font.color.rgb = RgbColor(128, 128, 128)

    # Save
    prs.save(output_path)
    return output_path


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def run_case_critique():
    """Run the case critique using task graph."""
    print("\n" + "="*60)
    print("TASK GRAPH DEMO: Case Study Critique")
    print("="*60)

    # Set up output path
    output_dir = Path("C:/Users/user/ii-agent/outputs/demos")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "ODG_Case_Critique.pptx"

    # Initialize telemetry
    telemetry = TelemetryLogger(
        output_dir=str(output_dir / "telemetry"),
        enable_console_logging=True,
    )

    # Create task graph
    graph = TaskGraph(name="CaseCritique")

    # Define phases
    graph.add_phase("analyze", parallel=True, max_parallel=3)
    graph.add_phase("synthesize", parallel=False, depends_on=["analyze"])
    graph.add_phase("output", parallel=False, depends_on=["synthesize"])

    # Register handlers
    graph.register_handler("analyze_structure", analyze_structure)
    graph.register_handler("analyze_content_quality", analyze_content_quality)
    graph.register_handler("analyze_consistency", analyze_consistency)
    graph.register_handler("generate_critique_summary", generate_critique_summary)
    graph.register_handler("generate_powerpoint", generate_powerpoint)

    # Add tasks - Analysis phase (parallel)
    graph.add_task(Task(
        id="structure",
        name="Analyze Structure",
        phase="analyze",
        handler_name="analyze_structure",
    ))

    graph.add_task(Task(
        id="quality",
        name="Analyze Content Quality",
        phase="analyze",
        handler_name="analyze_content_quality",
    ))

    graph.add_task(Task(
        id="consistency",
        name="Check Consistency",
        phase="analyze",
        handler_name="analyze_consistency",
    ))

    # Synthesis phase (depends on all analysis)
    graph.add_task(Task(
        id="summary",
        name="Generate Summary",
        phase="synthesize",
        handler_name="generate_critique_summary",
        dependencies=["structure", "quality", "consistency"],
    ))

    # Output phase
    graph.add_task(Task(
        id="powerpoint",
        name="Generate PowerPoint",
        phase="output",
        handler_name="generate_powerpoint",
        dependencies=["summary"],
    ))

    # Create budget
    budget = ExecutionBudget(
        max_total_tasks=10,
        max_parallel_tasks=3,
        task_timeout_ms=30000,
    )

    # Create context with case data
    context = {
        "case_data": CASE_STUDY_DATA,
        "output_path": str(output_path),
    }

    # Execute with telemetry
    async with telemetry.run_context(
        run_type="case_critique",
        metadata={"case": "ODG Analysis v1"},
    ) as run_ctx:

        # Create executor
        executor = TaskGraphExecutor(
            graph=graph,
            budget=budget,
            callbacks=LoggingCallbacks(),
            context=context,
        )

        # Run all tasks
        results = await executor.run_all()

        # Collect results into context for dependent tasks
        context["structure_result"] = results.get("structure", {}).result if results.get("structure") else {}
        context["quality_result"] = results.get("quality", {}).result if results.get("quality") else {}
        context["consistency_result"] = results.get("consistency", {}).result if results.get("consistency") else {}

        # Run synthesis manually (since context needs updating)
        summary_result = await generate_critique_summary(context)
        context["summary_result"] = summary_result

        # Run PowerPoint generation
        pptx_path = await generate_powerpoint(context)

        # Log metrics
        run_ctx.increment_tasks(completed=len(results))
        run_ctx.add_metric("output_file", pptx_path)

    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"\nGrade: {summary_result['grade']}")
    print(f"Critical Issues: {summary_result['critical_issues']}")
    print(f"Warnings: {summary_result['warnings']}")
    print(f"\nTop Issues:")
    for issue in summary_result['top_issues']:
        print(f"  - {issue}")
    print(f"\nPowerPoint saved to: {pptx_path}")
    print("="*60)

    return pptx_path


if __name__ == "__main__":
    result = asyncio.run(run_case_critique())
    print(f"\nDone! Output: {result}")
