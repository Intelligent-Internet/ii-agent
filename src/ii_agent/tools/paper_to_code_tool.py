"""Paper2Code Tool for ii-agent.

This tool converts scientific papers into reproducible code repositories
using a multi-stage LLM pipeline.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.tools.paper_to_code_pipeline import (
    Paper2CodePipeline,
    PipelineConfig,
    PipelineStage,
)

logger = logging.getLogger(__name__)


class PaperToCodeTool(LLMTool):
    """Tool for converting scientific papers to code repositories."""

    name = "paper_to_code"
    description = (
        "Convert scientific papers (PDF or LaTeX) into reproducible code repositories. "
        "This tool analyzes research papers and generates complete code implementations "
        "following the paper's methodology. Supports both PDF and LaTeX input formats."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "paper_path": {
                "type": "string",
                "description": "Path to the paper file (PDF or LaTeX)",
            },
            "output_dir": {
                "type": "string",
                "description": "Directory where the generated code repository will be saved",
            },
            "model": {
                "type": "string",
                "description": "LLM model to use (e.g., 'gpt-4o', 'o3-mini', 'deepseek-coder')",
                "default": "gpt-4o",
            },
            "stages": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["planning", "analyzing", "coding"],
                },
                "description": "Which stages to run. Defaults to all stages.",
                "default": ["planning", "analyzing", "coding"],
            },
            "use_local_llm": {
                "type": "boolean",
                "description": "Use local LLM via vLLM instead of API",
                "default": False,
            },
        },
        "required": ["paper_path", "output_dir"],
    }

    def __init__(self):
        """Initialize the Paper2Code tool."""
        super().__init__()

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        """Run the Paper2Code tool."""
        paper_path = Path(tool_input["paper_path"])
        output_dir = Path(tool_input["output_dir"])
        model = tool_input.get("model", "gpt-4o")
        stages = tool_input.get("stages", ["planning", "analyzing", "coding"])
        use_local_llm = tool_input.get("use_local_llm", False)

        # Validate input file
        if not paper_path.exists():
            return ToolImplOutput(
                tool_output=f"Paper file not found: {paper_path}",
                tool_result_message="Failed to find input file",
            )

        # Determine paper format
        suffix = paper_path.suffix.lower()
        if suffix == ".pdf":
            return ToolImplOutput(
                tool_output=(
                    "PDF input requires conversion to JSON format first. "
                    "Please convert your PDF using s2orc-doc2json tool and provide the JSON file."
                ),
                tool_result_message="PDF conversion not yet implemented",
            )
        elif suffix in [".tex", ".latex"]:
            paper_format = "latex"
        elif suffix == ".json":
            paper_format = "json"
        else:
            return ToolImplOutput(
                tool_output=f"Unsupported file format: {suffix}. Supported formats: .tex, .latex, .json",
                tool_result_message="Unsupported file format",
            )

        # Read paper content
        try:
            with open(paper_path, "r", encoding="utf-8") as f:
                paper_content = f.read()
        except Exception as e:
            return ToolImplOutput(
                tool_output=f"Error reading paper file: {str(e)}",
                tool_result_message="Failed to read paper file",
            )

        # Create pipeline configuration
        paper_name = paper_path.stem
        config = PipelineConfig(
            paper_name=paper_name,
            model=model,
            use_local_llm=use_local_llm,
            verbose=True,
        )

        # Initialize pipeline
        try:
            pipeline = Paper2CodePipeline(config)
        except Exception as e:
            return ToolImplOutput(
                tool_output=f"Failed to initialize pipeline: {str(e)}",
                tool_result_message="Pipeline initialization failed",
            )

        # Run requested stages
        success = True
        stage_map = {
            "planning": PipelineStage.PLANNING,
            "analyzing": PipelineStage.ANALYZING,
            "coding": PipelineStage.CODING,
        }

        try:
            for stage_name in stages:
                if stage_name not in stage_map:
                    logger.warning(f"Skipping unknown stage: {stage_name}")
                    continue

                stage = stage_map[stage_name]
                import ipdb; ipdb.set_trace()
                if stage == PipelineStage.PLANNING:
                    success = pipeline.run_planning(paper_content, paper_format)
                elif stage == PipelineStage.ANALYZING:
                    success = pipeline.run_analyzing()
                elif stage == PipelineStage.CODING:
                    success = pipeline.run_coding()
                
                if not success:
                    break

            # Save outputs
            pipeline.save_outputs(output_dir)

            # Prepare result
            if success:
                result_message = (
                    f"Successfully completed {', '.join(pipeline.state.completed_stages)} stages for {paper_name}. "
                    f"Output saved to {output_dir}"
                )
                
                # List generated artifacts
                artifacts = []
                if (output_dir / "planning").exists():
                    artifacts.append("planning artifacts")
                if (output_dir / "analysis").exists():
                    artifacts.append("analysis documents")
                if (output_dir / "generated_code").exists():
                    artifacts.append("generated code")
                
                tool_output = (
                    f"Paper2Code conversion completed successfully!\n\n"
                    f"Paper: {paper_name}\n"
                    f"Completed stages: {', '.join(pipeline.state.completed_stages)}\n"
                    f"Generated: {', '.join(artifacts)}\n"
                    f"Model used: {model}\n"
                    f"Total cost: ${pipeline.state.total_cost:.4f}\n"
                    f"Output directory: {output_dir}"
                )
            else:
                failed_stage = stages[len(pipeline.state.completed_stages)] if len(pipeline.state.completed_stages) < len(stages) else "unknown"
                result_message = f"Paper2Code failed at {failed_stage} stage"
                tool_output = (
                    f"Paper2Code conversion failed at {failed_stage} stage.\n"
                    f"Completed stages: {', '.join(pipeline.state.completed_stages) if pipeline.state.completed_stages else 'None'}\n"
                    f"Check logs for more details."
                )

            return ToolImplOutput(
                tool_output=tool_output,
                tool_result_message=result_message,
                auxiliary_data={
                    "completed_stages": pipeline.state.completed_stages,
                    "success": success,
                    "model": model,
                    "total_cost": pipeline.state.total_cost,
                    "output_dir": str(output_dir),
                },
            )

        except Exception as e:
            logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
            return ToolImplOutput(
                tool_output=f"Pipeline execution failed: {str(e)}",
                tool_result_message="Unexpected error during pipeline execution",
            )
            
def main():
    """Main function for testing the Paper2Code tool."""
    tool = PaperToCodeTool()
    tool_input = {
        "paper_path": "/home/pvduy/duy/repos/ii-agent/external/Paper2Code/codes/main.tex",
        "output_dir": "external/paper_to_code_output",
    }
    result = tool.run_impl(tool_input)
    print(result)
    
if __name__ == "__main__":
    main()