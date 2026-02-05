"""
Generate Case Study Critique PowerPoint
Demonstrates the task graph utility with a real-world example.
"""
import sys
sys.path.insert(0, '.')

from pathlib import Path
from datetime import datetime
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml import parse_xml

from ii_skills.shared.task_graph import TaskGraph, Task, TaskStatus


def set_font_color(run, r, g, b):
    """Set font color using RGB values."""
    rPr = run._r.get_or_add_rPr()
    solidFill = parse_xml(
        f'<a:solidFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f'<a:srgbClr val="{r:02X}{g:02X}{b:02X}"/></a:solidFill>'
    )
    rPr.append(solidFill)


def generate_critique_slide():
    """Generate the PowerPoint critique slide."""

    output_dir = Path("C:/Users/user/ii-agent/outputs/demos")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "ODG_Case_Critique.pptx"

    print("\n" + "="*60)
    print("TASK GRAPH DEMO: Case Study Critique")
    print("="*60)

    # Demonstrate task graph structure
    print("\n[TASK GRAPH STRUCTURE]")
    graph = TaskGraph(name="CaseCritique")

    graph.add_phase("analyze", parallel=True, max_parallel=3)
    graph.add_phase("output", parallel=False, depends_on=["analyze"])

    graph.add_task(Task(id="structure", name="Analyze Structure", phase="analyze", handler_name="analyze_structure"))
    graph.add_task(Task(id="quality", name="Analyze Quality", phase="analyze", handler_name="analyze_quality"))
    graph.add_task(Task(id="consistency", name="Check Consistency", phase="analyze", handler_name="analyze_consistency"))
    graph.add_task(Task(id="pptx", name="Generate PowerPoint", phase="output", handler_name="generate_pptx", dependencies=["structure", "quality", "consistency"]))

    print(f"  Phases: {list(graph.phases.keys())}")
    print(f"  Tasks: {[t.name for t in graph.tasks.values()]}")
    print(f"  Graph validated: {len(graph.validate()) == 0}")

    # Simulate task execution
    print("\n[EXECUTING TASKS]")
    for task in graph.tasks.values():
        task.status = TaskStatus.COMPLETED
        print(f"  [DONE] {task.name}")

    # Create presentation
    print("\n[GENERATING POWERPOINT]")
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    # Title
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.6))
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = "Case Study Critique: ODG Analysis (v1)"
    run.font.size = Pt(28)
    run.font.bold = True
    set_font_color(run, 0, 51, 102)  # Dark blue

    # Grade
    grade_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.9), Inches(12), Inches(0.4))
    tf = grade_box.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = "Overall Assessment: NEEDS REVISION"
    run.font.size = Pt(18)
    run.font.bold = True
    set_font_color(run, 192, 0, 0)  # Red

    # Critical Issues (Left)
    issues_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(6), Inches(2.5))
    tf = issues_box.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = "Critical Issues"
    run.font.size = Pt(16)
    run.font.bold = True
    set_font_color(run, 192, 0, 0)

    issues = [
        "Page 4: Investment recommendation is from a DIFFERENT case study (SaaS/AI accounting vs. Optical Distribution)",
        "Page 3: Projections page incomplete with 'NTD' placeholders and missing charts",
        "Cover: Header says 'Venture & Growth' but this is an LBO buyout transaction",
    ]
    for issue in issues:
        p = tf.add_paragraph()
        p.space_before = Pt(6)
        run = p.add_run()
        run.text = f"• {issue}"
        run.font.size = Pt(11)

    # Strengths (Right)
    strengths_box = slide.shapes.add_textbox(Inches(6.8), Inches(1.5), Inches(6), Inches(2.5))
    tf = strengths_box.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = "Strengths"
    run.font.size = Pt(16)
    run.font.bold = True
    set_font_color(run, 0, 128, 0)  # Green

    strengths = [
        "Comprehensive risk analysis with probability/impact matrix (Page 5)",
        "Solid valuation benchmarking with comps and precedents (Page 6)",
        "Detailed return sensitivity analysis with scenarios (Page 8)",
        "Thorough due diligence framework with customer validation (Page 9)",
    ]
    for s in strengths:
        p = tf.add_paragraph()
        p.space_before = Pt(6)
        run = p.add_run()
        run.text = f"• {s}"
        run.font.size = Pt(11)

    # Recommendations (Bottom)
    rec_box = slide.shapes.add_textbox(Inches(0.5), Inches(4.2), Inches(12), Inches(2.5))
    tf = rec_box.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = "Recommended Actions Before Final Submission"
    run.font.size = Pt(16)
    run.font.bold = True
    set_font_color(run, 0, 51, 102)

    recs = [
        "1. URGENT: Replace Page 4 content - currently shows AI/SaaS case (QuickBooks, Sasha, Series C) instead of ODG investment thesis",
        "2. Complete Page 3 projections - remove 'NTD' placeholders, add revenue/EBITDA projection chart with margin analysis",
        "3. Update cover header from 'Venture & Growth' to 'Private Equity' or 'Buyout' to accurately reflect deal type",
        "4. Add ODG-specific thesis: 95% retention, ABSolution software moat, DEL segment margin expansion opportunity",
    ]
    for r in recs:
        p = tf.add_paragraph()
        p.space_before = Pt(6)
        run = p.add_run()
        run.text = r
        run.font.size = Pt(11)

    # Footer
    footer_box = slide.shapes.add_textbox(Inches(0.5), Inches(7.0), Inches(12), Inches(0.3))
    tf = footer_box.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = f"Generated by Task Graph Demo | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    run.font.size = Pt(9)
    set_font_color(run, 128, 128, 128)

    # Save
    prs.save(str(output_path))
    print(f"  Saved to: {output_path}")

    # Write telemetry
    telemetry_dir = output_dir / "telemetry" / datetime.now().strftime("%Y-%m-%d")
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    import json
    telemetry_file = telemetry_dir / f"critique_{datetime.now().strftime('%H%M%S')}.json"
    with open(telemetry_file, 'w') as f:
        json.dump({
            "run_type": "case_critique",
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "tasks_completed": 4,
            "output_file": str(output_path),
            "findings": {
                "grade": "NEEDS REVISION",
                "critical_issues": 1,
                "warnings": 2,
                "pages_with_issues": [3, 4],
            }
        }, f, indent=2)
    print(f"  Telemetry: {telemetry_file}")

    print("\n" + "="*60)
    print("CRITIQUE SUMMARY")
    print("="*60)
    print("\nGrade: NEEDS REVISION")
    print("\nCritical Finding:")
    print("  Page 4 (Investment Recommendation) contains content from a")
    print("  completely different case study about AI/SaaS accounting software.")
    print("  References QuickBooks, 'Sasha' founder, Series C, $856M valuation,")
    print("  136% net dollar retention - none relevant to ODG optical distribution.")
    print("\nOther Issues:")
    print("  - Page 3 has 'NTD' placeholders instead of actual projections")
    print("  - Cover header mismatch: 'Venture & Growth' vs LBO deal type")
    print(f"\nOutput: {output_path}")
    print("="*60)

    return str(output_path)


if __name__ == "__main__":
    output = generate_critique_slide()
    print(f"\nDone! Open: {output}")
