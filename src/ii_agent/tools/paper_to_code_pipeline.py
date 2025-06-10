"""Consolidated Paper2Code Pipeline Implementation.

This module provides a unified implementation of the Paper2Code pipeline,
combining planning, analyzing, and coding stages into a single cohesive class.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from openai import OpenAI
from tqdm import tqdm

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Enum for pipeline stages."""
    PLANNING = "planning"
    ANALYZING = "analyzing"
    CODING = "coding"


@dataclass
class PipelineConfig:
    """Configuration for the Paper2Code pipeline."""
    paper_name: str
    model: str = "o4-mini"
    temperature: float = 1.0
    use_local_llm: bool = False
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    max_retries: int = 3
    verbose: bool = True


@dataclass
class PipelineState:
    """State management for the pipeline."""
    # Planning outputs
    overall_plan: str = ""
    file_list: List[Dict[str, Any]] = field(default_factory=list)
    task_list: List[Dict[str, Any]] = field(default_factory=list)
    config_yaml: str = ""
    architecture_diagram: Optional[str] = None
    sequence_diagram: Optional[str] = None
    
    # Analysis outputs
    file_analyses: Dict[str, str] = field(default_factory=dict)
    
    # Coding outputs
    generated_files: Dict[str, str] = field(default_factory=dict)
    
    # Tracking
    completed_stages: List[str] = field(default_factory=list)
    total_cost: float = 0.0
    trajectories: List[Dict[str, Any]] = field(default_factory=list)


class Paper2CodePipeline:
    """Unified Paper2Code pipeline implementation."""
    
    def __init__(self, config: PipelineConfig):
        """Initialize the pipeline with configuration."""
        self.config = config
        self.state = PipelineState()
        self._setup_openai()
        
    def _setup_openai(self):
        """Set up OpenAI client configuration."""
        from openai import AzureOpenAI 
        self.client = AzureOpenAI(
            api_version="2024-12-01-preview",
            azure_endpoint="https://test27653533018.cognitiveservices.azure.com/",
            api_key="3ijnMBqM7teOPw6Mxt74cuna85TiEn8evkuoQnPD9AK6FGnsgYSBJQQJ99BAACHYHv6XJ3w3AAAAACOGbVlY"
        )
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()
    
    def _make_api_call(self, messages: List[Dict[str, str]], stage: str) -> Tuple[str, float]:
        """Make an API call to the LLM.
        
        Args:
            messages: List of message dictionaries
            stage: Current pipeline stage for logging
            
        Returns:
            Tuple of (response_content, cost)
        """
        if self.config.verbose:
            logger.info(f"Making API call for {stage}")
            
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=128000,
            )
            
            content = response.choices[0].message.content
            
            # Calculate cost (simplified - adjust based on actual pricing)
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            cost = self._calculate_cost(prompt_tokens, completion_tokens)
            
            # Track trajectory in original format
            trajectory_entry = {
                "instruction": messages[-1]["content"] if messages else "",
                "response": content,
                "info": {
                    "stage": stage,
                    "model": self.config.model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost": cost,
                    "timestamp": self._get_timestamp()
                }
            }
            self.state.trajectories.append(trajectory_entry)
            
            return content, cost
            
        except Exception as e:
            logger.error(f"API call failed for {stage}: {str(e)}")
            raise
    
    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate API cost based on token usage with accurate pricing."""
        # Updated pricing as of 2024 (prices per 1K tokens)
        model_costs = {
            # OpenAI models
            "o4-mini": {"prompt": 0.00015, "completion": 0.0006},
            "gpt-4o": {"prompt": 0.005, "completion": 0.015},
            "gpt-4o-2024-05-13": {"prompt": 0.005, "completion": 0.015},
            "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
            "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
            "gpt-4": {"prompt": 0.03, "completion": 0.06},
            "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
            "gpt-3.5-turbo-16k": {"prompt": 0.003, "completion": 0.004},
            
            # Anthropic models
            "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
            "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
            "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
            
            # DeepSeek models
            "deepseek-coder": {"prompt": 0.00014, "completion": 0.00028},
            "deepseek-chat": {"prompt": 0.00014, "completion": 0.00028},
            
            # Local/custom models (no cost)
            "local": {"prompt": 0.0, "completion": 0.0},
        }
        
        # Find the cost configuration for the model
        costs = None
        for model_key in model_costs:
            if model_key in self.config.model.lower():
                costs = model_costs[model_key]
                break
        
        # Default to GPT-4o pricing if model not found
        if costs is None:
            logger.warning(f"Unknown model '{self.config.model}', using GPT-4o pricing")
            costs = model_costs["gpt-4o"]
        
        # Calculate cost (prices are per 1K tokens)
        cost = (prompt_tokens * costs["prompt"] + completion_tokens * costs["completion"]) / 1000
        
        self.state.total_cost += cost
        return cost
    
    def _extract_json_from_content(self, content: str) -> Dict[str, Any]:
        """Extract JSON from LLM response content."""
        import re
        
        # First try to extract from [CONTENT][/CONTENT] blocks
        content_pattern = r'\[CONTENT\]\s*(.*?)\s*\[/CONTENT\]'
        content_matches = re.findall(content_pattern, content, re.DOTALL)
        
        if content_matches:
            content = content_matches[0]
        
        # Look for ```json blocks
        json_pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(json_pattern, content, re.DOTALL)
        
        if matches:
            try:
                return json.loads(matches[0])
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from code block: {e}")
        
        # Try to parse the entire content as JSON
        try:
            # Remove any markdown formatting
            clean_content = content.strip()
            if clean_content.startswith('```') and clean_content.endswith('```'):
                clean_content = clean_content[3:-3].strip()
                if clean_content.startswith('json'):
                    clean_content = clean_content[4:].strip()
            
            return json.loads(clean_content)
        except json.JSONDecodeError:
            # If all else fails, return empty dict
            logger.warning("Failed to extract JSON from content")
            return {}
    
    def _extract_code_from_content(self, content: str) -> str:
        """Extract code from LLM response content."""
        import re
        
        # First try to extract from [CONTENT][/CONTENT] blocks
        content_pattern = r'\[CONTENT\]\s*(.*?)\s*\[/CONTENT\]'
        content_matches = re.findall(content_pattern, content, re.DOTALL)
        
        if content_matches:
            content = content_matches[0]
        
        # Look for code blocks (python, yaml, etc.)
        code_pattern = r'```(?:python|yaml|yml)?\s*(.*?)\s*```'
        matches = re.findall(code_pattern, content, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # If no code blocks found, clean up the content
        # Remove any [CONTENT] tags that might remain
        content = re.sub(r'\[/?CONTENT\]', '', content)
        
        return content.strip()
    
    def run_planning(self, paper_content: str, paper_format: str = "latex") -> bool:
        """Run the planning stage of the pipeline.
        
        Args:
            paper_content: Content of the paper
            paper_format: Format of the paper (latex or json)
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Starting planning stage")
        
        try:
            # Step 1: Generate overall plan
            # Split the prompt into system and user messages as in original
            planning_prompt = self._create_planning_prompt(paper_content, paper_format)
            # The prompt contains both system instructions and user task, split them
            parts = planning_prompt.split("\n\n## Paper", 1)
            system_content = parts[0] if len(parts) > 0 else ""
            user_content = "## Paper" + parts[1] if len(parts) > 1 else planning_prompt
            
            plan_messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ]
            
            plan_response, cost = self._make_api_call(plan_messages, "planning_overall")
            self.state.overall_plan = plan_response
            
            # Step 2: Generate file list (architecture)
            file_list_messages = plan_messages + [
                {"role": "assistant", "content": plan_response},
                {"role": "user", "content": self._create_file_list_prompt()}
            ]
            
            file_list_response, cost = self._make_api_call(file_list_messages, "planning_files")
            file_list_json = self._extract_json_from_content(file_list_response)
            # Handle Paper2Code format
            self.state.file_list = file_list_json.get("File list", file_list_json.get("files", []))
            
            # Extract mermaid diagrams if present (Paper2Code format)
            if "Data structures and interfaces" in file_list_json:
                self.state.architecture_diagram = file_list_json["Data structures and interfaces"]
            elif "architecture_diagram" in file_list_json:
                self.state.architecture_diagram = file_list_json["architecture_diagram"]
                
            if "Program call flow" in file_list_json:
                self.state.sequence_diagram = file_list_json["Program call flow"]
            elif "sequence_diagram" in file_list_json:
                self.state.sequence_diagram = file_list_json["sequence_diagram"]
            
            # Step 3: Generate task list
            task_list_messages = file_list_messages + [
                {"role": "assistant", "content": file_list_response},
                {"role": "user", "content": self._create_task_list_prompt()}
            ]
            
            task_list_response, cost = self._make_api_call(task_list_messages, "planning_tasks")
            task_list_json = self._extract_json_from_content(task_list_response)
            # Handle Paper2Code format - it uses "Task list" as key
            self.state.task_list = task_list_json.get("Task list", task_list_json.get("tasks", []))
            
            # Step 4: Generate config.yaml
            config_messages = task_list_messages + [
                {"role": "assistant", "content": task_list_response},
                {"role": "user", "content": self._create_config_prompt()}
            ]
            
            config_response, cost = self._make_api_call(config_messages, "planning_config")
            self.state.config_yaml = self._extract_code_from_content(config_response)
            
            self.state.completed_stages.append(PipelineStage.PLANNING.value)
            logger.info(f"Planning stage completed. Total cost: ${self.state.total_cost:.4f}")
            return True
            
        except Exception as e:
            logger.error(f"Planning stage failed: {str(e)}")
            return False
    
    def run_analyzing(self, paper_format: str = "latex") -> bool:
        """Run the analyzing stage of the pipeline.
        
        Args:
            paper_format: Format of the paper (latex or json)
            
        Returns:
            True if successful, False otherwise
        """
        if PipelineStage.PLANNING.value not in self.state.completed_stages:
            logger.error("Cannot run analyzing without completing planning first")
            return False
            
        logger.info("Starting analyzing stage")
        
        try:
            # Build context from planning
            planning_context = self._build_planning_context()
            
            # Analyze each file in the task list
            # Paper2Code format: task_list is just a list of filenames
            # Need to get descriptions from Logic Analysis
            task_list_full = self._extract_json_from_content(self.state.trajectories[-2]["response"]) if self.state.trajectories else {}
            logic_analysis_dict = {}
            if "Logic Analysis" in task_list_full:
                for desc in task_list_full["Logic Analysis"]:
                    logic_analysis_dict[desc[0]] = desc[1]
            
            for file_name in tqdm(self.state.task_list, desc="Analyzing files"):
                if isinstance(file_name, dict):
                    # Handle dict format if present
                    file_name = file_name.get("file_name", "")
                    file_desc = file_name.get("description", "")
                else:
                    # Handle string format (Paper2Code)
                    file_desc = logic_analysis_dict.get(file_name, "")
                
                if not file_name:
                    continue
                
                # Using exact system message from external/Paper2Code/codes/2_analyzing.py
                analysis_messages = [
                    {"role": "system", "content": f"""You are an expert researcher, strategic analyzer and software engineer with a deep understanding of experimental design and reproducibility in scientific research.
You will receive a research paper in {paper_format} format, an overview of the plan, a design in JSON format consisting of "Implementation approach", "File list", "Data structures and interfaces", and "Program call flow", followed by a task in JSON format that includes "Required packages", "Required other language third-party packages", "Logic Analysis", and "Task list", along with a configuration file named "config.yaml". 

Your task is to conduct a comprehensive logic analysis to accurately reproduce the experiments and methodologies described in the research paper. 
This analysis must align precisely with the paper's methodology, experimental setup, and evaluation criteria.

1. Align with the Paper: Your analysis must strictly follow the methods, datasets, model configurations, hyperparameters, and experimental setups described in the paper.
2. Be Clear and Structured: Present your analysis in a logical, well-organized, and actionable format that is easy to follow and implement.
3. Prioritize Efficiency: Optimize the analysis for clarity and practical implementation while ensuring fidelity to the original experiments.
4. Follow design: YOU MUST FOLLOW "Data structures and interfaces". DONT CHANGE ANY DESIGN. Do not use public member functions that do not exist in your design.
5. REFER TO CONFIGURATION: Always reference settings from the config.yaml file. Do not invent or assume any values—only use configurations explicitly provided.
     
"""},
                    {"role": "user", "content": planning_context},
                    {"role": "user", "content": self._create_analysis_prompt(file_name, file_desc)}
                ]
                
                analysis_response, cost = self._make_api_call(
                    analysis_messages, 
                    f"analyzing_{file_name}"
                )
                
                self.state.file_analyses[file_name] = analysis_response
            
            self.state.completed_stages.append(PipelineStage.ANALYZING.value)
            logger.info(f"Analyzing stage completed. Total cost: ${self.state.total_cost:.4f}")
            return True
            
        except Exception as e:
            logger.error(f"Analyzing stage failed: {str(e)}")
            return False
    
    def run_coding(self, paper_content: str = "", paper_format: str = "latex") -> bool:
        """Run the coding stage of the pipeline.
        
        Args:
            paper_content: Content of the paper (optional, for prompts)
            paper_format: Format of the paper (latex or json)
            
        Returns:
            True if successful, False otherwise
        """
        if PipelineStage.ANALYZING.value not in self.state.completed_stages:
            logger.error("Cannot run coding without completing analyzing first")
            return False
            
        logger.info("Starting coding stage")
        
        try:
            # Build context from planning and analysis
            planning_context = self._build_planning_context()
            
            # Generate code for each file
            for task_item in tqdm(self.state.task_list, desc="Generating code"):
                if isinstance(task_item, dict):
                    file_name = task_item.get("file_name", "")
                else:
                    # Handle string format (Paper2Code)
                    file_name = task_item
                
                if not file_name or file_name in self.state.generated_files:
                    continue
                
                # Get dependencies that are already generated
                # For Paper2Code format, dependencies come from task order
                completed_deps = {}
                if isinstance(task_item, dict):
                    dependencies = task_item.get("dependencies", [])
                    completed_deps = {
                        dep: self.state.generated_files.get(dep, "")
                        for dep in dependencies
                        if dep in self.state.generated_files
                    }
                else:
                    # For Paper2Code format, all previously generated files are dependencies
                    completed_deps = dict(self.state.generated_files)
                
                # Using exact system message from external/Paper2Code/codes/3_coding.py
                coding_messages = [
                    {"role": "system", "content": f"""You are an expert researcher and software engineer with a deep understanding of experimental design and reproducibility in scientific research.
You will receive a research paper in {paper_format} format, an overview of the plan, a Design in JSON format consisting of "Implementation approach", "File list", "Data structures and interfaces", and "Program call flow", followed by a Task in JSON format that includes "Required packages", "Required other language third-party packages", "Logic Analysis", and "Task list", along with a configuration file named "config.yaml". 
Your task is to write code to reproduce the experiments and methodologies described in the paper. 

The code you write must be elegant, modular, and maintainable, adhering to Google-style guidelines. 
The code must strictly align with the paper's methodology, experimental setup, and evaluation metrics. 
Write code with triple quoto."""},
                    {"role": "user", "content": self._create_coding_prompt(
                        file_name,
                        self.state.file_analyses.get(file_name, ""),
                        completed_deps,
                        paper_content
                    )}
                ]
                
                code_response, cost = self._make_api_call(
                    coding_messages,
                    f"coding_{file_name}"
                )
                
                code = self._extract_code_from_content(code_response)
                self.state.generated_files[file_name] = code
            
            self.state.completed_stages.append(PipelineStage.CODING.value)
            logger.info(f"Coding stage completed. Total cost: ${self.state.total_cost:.4f}")
            return True
            
        except Exception as e:
            logger.error(f"Coding stage failed: {str(e)}")
            return False
    
    def save_outputs(self, output_dir: Path) -> None:
        """Save all pipeline outputs to the specified directory."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save planning artifacts
        planning_dir = output_dir / "planning"
        planning_dir.mkdir(exist_ok=True)
        
        with open(planning_dir / "overall_plan.txt", "w") as f:
            f.write(self.state.overall_plan)
        
        with open(planning_dir / "file_list.json", "w") as f:
            json.dump(self.state.file_list, f, indent=2)
        
        with open(planning_dir / "task_list.json", "w") as f:
            json.dump(self.state.task_list, f, indent=2)
        
        with open(planning_dir / "config.yaml", "w") as f:
            f.write(self.state.config_yaml)
        
        # Save mermaid diagrams if present
        if self.state.architecture_diagram:
            with open(planning_dir / "architecture_diagram.md", "w") as f:
                f.write("# Architecture Diagram\n\n")
                f.write(self.state.architecture_diagram)
        
        if self.state.sequence_diagram:
            with open(planning_dir / "sequence_diagram.md", "w") as f:
                f.write("# Sequence Diagram\n\n")
                f.write(self.state.sequence_diagram)
        
        # Save analysis outputs
        if self.state.file_analyses:
            analysis_dir = output_dir / "analysis"
            analysis_dir.mkdir(exist_ok=True)
            
            for file_name, analysis in self.state.file_analyses.items():
                safe_name = file_name.replace("/", "_").replace("\\", "_")
                with open(analysis_dir / f"{safe_name}_analysis.txt", "w") as f:
                    f.write(analysis)
        
        # Save generated code
        if self.state.generated_files:
            code_dir = output_dir / "generated_code"
            code_dir.mkdir(exist_ok=True)
            
            for file_path, code in self.state.generated_files.items():
                file_path = Path(file_path)
                full_path = code_dir / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(full_path, "w") as f:
                    f.write(code)
        
        # Save trajectories and cost info
        with open(output_dir / "trajectories.json", "w") as f:
            json.dump(self.state.trajectories, f, indent=2)
        
        with open(output_dir / "cost_info.txt", "w") as f:
            f.write(f"Total API cost: ${self.state.total_cost:.4f}\n")
            f.write(f"Completed stages: {', '.join(self.state.completed_stages)}\n")
            f.write(f"Model used: {self.config.model}\n")
    
    # Prompt creation methods
    def _create_planning_prompt(self, paper_content: str, paper_format: str) -> str:
        """Create the initial planning prompt."""
        # Using exact prompt from external/Paper2Code/codes/1_planning.py
        system_msg = f"""You are an expert researcher and strategic planner with a deep understanding of experimental design and reproducibility in scientific research. 
You will receive a research paper in {paper_format} format. 
Your task is to create a detailed and efficient plan to reproduce the experiments and methodologies described in the paper.
This plan should align precisely with the paper's methodology, experimental setup, and evaluation metrics. 

Instructions:

1. Align with the Paper: Your plan must strictly follow the methods, datasets, model configurations, hyperparameters, and experimental setups described in the paper.
2. Be Clear and Structured: Present the plan in a well-organized and easy-to-follow format, breaking it down into actionable steps.
3. Prioritize Efficiency: Optimize the plan for clarity and practical implementation while ensuring fidelity to the original experiments."""
        
        user_msg = f"""## Paper
{paper_content}

## Task
1. We want to reproduce the method described in the attached paper. 
2. The authors did not release any official code, so we have to plan our own implementation.
3. Before writing any Python code, please outline a comprehensive plan that covers:
   - Key details from the paper's **Methodology**.
   - Important aspects of **Experiments**, including dataset requirements, experimental settings, hyperparameters, or evaluation metrics.
4. The plan should be as **detailed and informative** as possible to help us write the final code later.

## Requirements
- You don't need to provide the actual code yet; focus on a **thorough, clear strategy**.
- If something is unclear from the paper, mention it explicitly.

## Instruction
The response should give us a strong roadmap, making it easier to write the code later."""
        
        # Return combined message content
        return system_msg + "\n\n" + user_msg

    def _create_file_list_prompt(self) -> str:
        """Create the file list generation prompt."""
        # Using exact prompt from external/Paper2Code/codes/1_planning.py
        return """Your goal is to create a concise, usable, and complete software system design for reproducing the paper's method. Use appropriate open-source libraries and keep the overall architecture simple.
             
Based on the plan for reproducing the paper's main method, please design a concise, usable, and complete software system. 
Keep the architecture simple and make effective use of open-source libraries.

-----

## Format Example
[CONTENT]
{
    "Implementation approach": "We will ... ,
    "File list": [
        "main.py",  
        "dataset_loader.py", 
        "model.py",  
        "trainer.py",
        "evaluation.py" 
    ],
    "Data structures and interfaces": "\nclassDiagram\n    class Main {\n        +__init__()\n        +run_experiment()\n    }\n    class DatasetLoader {\n        +__init__(config: dict)\n        +load_data() -> Any\n    }\n    class Model {\n        +__init__(params: dict)\n        +forward(x: Tensor) -> Tensor\n    }\n    class Trainer {\n        +__init__(model: Model, data: Any)\n        +train() -> None\n    }\n    class Evaluation {\n        +__init__(model: Model, data: Any)\n        +evaluate() -> dict\n    }\n    Main --> DatasetLoader\n    Main --> Trainer\n    Main --> Evaluation\n    Trainer --> Model\n",
    "Program call flow": "\nsequenceDiagram\n    participant M as Main\n    participant DL as DatasetLoader\n    participant MD as Model\n    participant TR as Trainer\n    participant EV as Evaluation\n    M->>DL: load_data()\n    DL-->>M: return dataset\n    M->>MD: initialize model()\n    M->>TR: train(model, dataset)\n    TR->>MD: forward(x)\n    MD-->>TR: predictions\n    TR-->>M: training complete\n    M->>EV: evaluate(model, dataset)\n    EV->>MD: forward(x)\n    MD-->>EV: predictions\n    EV-->>M: metrics\n",
    "Anything UNCLEAR": "Need clarification on the exact dataset format and any specialized hyperparameters."
}
[/CONTENT]

## Nodes: "<node>: <type>  # <instruction>"
- Implementation approach: <class 'str'>  # Summarize the chosen solution strategy.
- File list: typing.List[str]  # Only need relative paths. ALWAYS write a main.py or app.py here.
- Data structures and interfaces: typing.Optional[str]  # Use mermaid classDiagram code syntax, including classes, method(__init__ etc.) and functions with type annotations, CLEARLY MARK the RELATIONSHIPS between classes, and comply with PEP8 standards. The data structures SHOULD BE VERY DETAILED and the API should be comprehensive with a complete design.
- Program call flow: typing.Optional[str] # Use sequenceDiagram code syntax, COMPLETE and VERY DETAILED, using CLASSES AND API DEFINED ABOVE accurately, covering the CRUD AND INIT of each object, SYNTAX MUST BE CORRECT.
- Anything UNCLEAR: <class 'str'>  # Mention ambiguities and ask for clarifications.

## Constraint
Format: output wrapped inside [CONTENT][/CONTENT] like the format example, nothing else.

## Action
Follow the instructions for the nodes, generate the output, and ensure it follows the format example."""

    def _create_task_list_prompt(self) -> str:
        """Create the task list generation prompt."""
        # Using exact prompt from external/Paper2Code/codes/1_planning.py
        return """Your goal is break down tasks according to PRD/technical design, generate a task list, and analyze task dependencies. 
You will break down tasks, analyze dependencies.
             
You outline a clear PRD/technical design for reproducing the paper's method and experiments. 

Now, let's break down tasks according to PRD/technical design, generate a task list, and analyze task dependencies.
The Logic Analysis should not only consider the dependencies between files but also provide detailed descriptions to assist in writing the code needed to reproduce the paper.

-----

## Format Example
[CONTENT]
{
    "Required packages": [
        "numpy==1.21.0",
        "torch==1.9.0"  
    ],
    "Required Other language third-party packages": [
        "No third-party dependencies required"
    ],
    "Logic Analysis": [
        [
            "data_preprocessing.py",
            "DataPreprocessing class ........"
        ],
        [
            "trainer.py",
            "Trainer ....... "
        ],
        [
            "dataset_loader.py",
            "Handles loading and ........"
        ],
        [
            "model.py",
            "Defines the model ......."
        ],
        [
            "evaluation.py",
            "Evaluation class ........ "
        ],
        [
            "main.py",
            "Entry point  ......."
        ]
    ],
    "Task list": [
        "dataset_loader.py", 
        "model.py",  
        "trainer.py", 
        "evaluation.py",
        "main.py"  
    ],
    "Full API spec": "openapi: 3.0.0 ...",
    "Shared Knowledge": "Both data_preprocessing.py and trainer.py share ........",
    "Anything UNCLEAR": "Clarification needed on recommended hardware configuration for large-scale experiments."
}

[/CONTENT]

## Nodes: "<node>: <type>  # <instruction>"
- Required packages: typing.Optional[typing.List[str]]  # Provide required third-party packages in requirements.txt format.(e.g., 'numpy==1.21.0').
- Required Other language third-party packages: typing.List[str]  # List down packages required for non-Python languages. If none, specify "No third-party dependencies required".
- Logic Analysis: typing.List[typing.List[str]]  # Provide a list of files with the classes/methods/functions to be implemented, including dependency analysis and imports. Include as much detailed description as possible.
- Task list: typing.List[str]  # Break down the tasks into a list of filenames, prioritized based on dependency order. The task list must include the previously generated file list.
- Full API spec: <class 'str'>  # Describe all APIs using OpenAPI 3.0 spec that may be used by both frontend and backend. If front-end and back-end communication is not required, leave it blank.
- Shared Knowledge: <class 'str'>  # Detail any shared knowledge, like common utility functions or configuration variables.
- Anything UNCLEAR: <class 'str'>  # Mention any unresolved questions or clarifications needed from the paper or project scope.

## Constraint
Format: output wrapped inside [CONTENT][/CONTENT] like the format example, nothing else.

## Action
Follow the node instructions above, generate your output accordingly, and ensure it follows the given format example."""

    def _create_config_prompt(self) -> str:
        """Create the configuration file generation prompt."""
        # Using exact prompt from external/Paper2Code/codes/1_planning.py
        return """You write elegant, modular, and maintainable code. Adhere to Google-style guidelines.

Based on the paper, plan, design specified previously, follow the "Format Example" and generate the code. 
Extract the training details from the above paper (e.g., learning rate, batch size, epochs, etc.), follow the "Format example" and generate the code. 
DO NOT FABRICATE DETAILS — only use what the paper provides.

You must write `config.yaml`.

ATTENTION: Use '##' to SPLIT SECTIONS, not '#'. Your output format must follow the example below exactly.

-----

# Format Example
## Code: config.yaml
```yaml
## config.yaml
training:
  learning_rate: ...
  batch_size: ...
  epochs: ...
...
```

-----

## Code: config.yaml
"""

    def _create_analysis_prompt(self, file_name: str, file_desc: str) -> str:
        """Create the analysis prompt for a specific file."""
        # Based on external/Paper2Code/codes/2_analyzing.py get_write_msg
        draft_desc = f"Write the logic analysis in '{file_name}', which is intended for '{file_desc}'."
        if len(file_desc.strip()) == 0:
            draft_desc = f"Write the logic analysis in '{file_name}'."
        
        return f"""## Instruction
Conduct a Logic Analysis to assist in writing the code, based on the paper, the plan, the design, the task and the previously specified configuration file (config.yaml). 
You DON'T need to provide the actual code yet; focus on a thorough, clear analysis.

{draft_desc}

-----

## Logic Analysis: {file_name}"""

    def _create_coding_prompt(self, file_name: str, analysis: str, dependencies: Dict[str, str], paper_content: str = "") -> str:
        """Create the coding prompt for a specific file."""
        # Based on external/Paper2Code/codes/3_coding.py get_write_msg
        
        code_files = ""
        for done_file, done_code in dependencies.items():
            if done_file.endswith(".yaml"): 
                continue
            code_files += f"""
```python
{done_code}
```

"""
        
        # Extract context from planning state
        context_lst = [
            self.state.overall_plan,  # context_lst[0]
            json.dumps(self.state.file_list, indent=2),  # context_lst[1]
            json.dumps(self.state.task_list, indent=2)   # context_lst[2]
        ]
        
        prompt = f"""# Context
## Paper
{paper_content}

-----

## Overview of the plan
{context_lst[0]}

-----

## Design
{context_lst[1]}

-----

## Task
{context_lst[2]}

-----

## Configuration file
```yaml
{self.state.config_yaml}
```
-----

## Code Files
{code_files}

-----

# Format example
## Code: {file_name}
```python
## {file_name}
...
```

-----

# Instruction
Based on the paper, plan, design, task and configuration file(config.yaml) specified previously, follow "Format example", write the code. 

We have {list(dependencies.keys())}.
Next, you must write only the "{file_name}".
1. Only One file: do your best to implement THIS ONLY ONE FILE.
2. COMPLETE CODE: Your code will be part of the entire project, so please implement complete, reliable, reusable code snippets.
3. Set default value: If there is any setting, ALWAYS SET A DEFAULT VALUE, ALWAYS USE STRONG TYPE AND EXPLICIT VARIABLE. AVOID circular import.
4. Follow design: YOU MUST FOLLOW "Data structures and interfaces". DONT CHANGE ANY DESIGN. Do not use public member functions that do not exist in your design.
5. CAREFULLY CHECK THAT YOU DONT MISS ANY NECESSARY CLASS/FUNCTION IN THIS FILE.
6. Before using a external variable/module, make sure you import it first.
7. Write out EVERY CODE DETAIL, DON'T LEAVE TODO.
8. REFER TO CONFIGURATION: you must use configuration from "config.yaml". DO NOT FABRICATE any configuration values.

{analysis}

## Code: {file_name}"""
        
        return prompt
    
    def _get_file_header(self) -> str:
        """Generate standard file header."""
        return f"""{self.config.paper_name} Implementation
Auto-generated by Paper2Code Pipeline

This file implements [specific component description]"""

    def _build_planning_context(self) -> str:
        """Build context string from planning outputs."""
        # For Paper2Code compatibility, we need to format this differently
        # Extract the full JSON responses from trajectories if available
        file_list_json = {}
        task_list_json = {}
        
        for trajectory in self.state.trajectories:
            if trajectory.get("info", {}).get("stage") == "planning_files":
                file_list_json = self._extract_json_from_content(trajectory["response"])
            elif trajectory.get("info", {}).get("stage") == "planning_tasks":
                task_list_json = self._extract_json_from_content(trajectory["response"])
        
        context = f"""## Paper
{{paper_content}}

-----

## Overview of the plan
{self.state.overall_plan}

-----

## Design
{json.dumps(file_list_json, indent=2)}

-----

## Task
{json.dumps(task_list_json, indent=2)}

-----

## Configuration file
```yaml
{self.state.config_yaml}
```"""
        return context