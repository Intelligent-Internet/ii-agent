import gitingest
import traceback # For more detailed error logging if needed
from pathlib import Path
from typing import Set, Optional, Tuple
from gitingest.utils.ignore_patterns import DEFAULT_IGNORE_PATTERNS # Keep import outside class
from google import genai
from google.genai import types

# --- Define additional patterns to exclude for focusing on Python code ---
# Moved outside the class as it's a constant definition
PYTHON_PROJECT_EXCLUDES: Set[str] = {
    # Common test directories/files
    "tests/",
    "test/",
    "*_test.py",
    "test_*.py",
    "conftest.py",
    ".pytest_cache/",

    # Common documentation directories/files
    "docs/",
    "doc/",
    "workspace/",
    "examples/",
    "notebooks/",
    "*.rst",
    # '*.md', # Be careful excluding all markdown, README.md can be vital

    # Common data directories/files
    "data/",
    "*.csv",
    "*.json",
    "*.yaml",
    "*.xml",
    "*.db",
    "*.sqlite*",
    "*.parquet",
    "*.pkl",
    "*.hdf5",

    # Common non-essential meta/config files
    ".gitignore",
    ".dockerignore",
    "Dockerfile*",
    ".pre-commit-config.yaml",
    "LICENSE*",
    "CONTRIBUTING*",
    "CODE_OF_CONDUCT*",
    "SECURITY.md",
    ".coveragerc",
    ".pylintrc",
    "mypy.ini",

    # CI/CD
    ".github/",
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
}
# -----------------------------------------------------------------------


class RepoAgent:
    """
    Agent for working with repository-level code, providing ingestion capabilities.
    """
    def __init__(self, repo_source: str):
        """
        Initializes the RepoAgent with the target repository source.

        Args:
            repo_source: The repository identifier (URL, slug, or local path).
        """
        self.repo_source: str = repo_source
        self.summary: Optional[str] = None
        self.tree: Optional[str] = None
        self.content: Optional[str] = None
        self.filtered_summary: Optional[str] = None
        self.filtered_tree: Optional[str] = None
        self.filtered_content: Optional[str] = None
        self.last_error: Optional[str] = None

    def _format_output(self, summary: str, tree: str, content: str, filtered: bool = False) -> str:
        """Helper method to format the ingested output."""
        title_suffix = "(Filtered)" if filtered else ""
        return f"""--- Repository Summary {title_suffix}---
{summary}

--- File Tree {title_suffix}---
{tree}

--- File Contents {title_suffix}---
{content}"""

    def ingest(self) -> Optional[str]:
        """
        Ingests the repository using default settings.

        Uses the gitingest library to fetch (clone if necessary)
        and process the repository specified during initialization.
        Stores the summary, tree, and content as instance attributes.

        Returns:
            A string containing the formatted summary, file tree, and content,
            or None if an error occurred.
        """
        print(f"Attempting to ingest: {self.repo_source}")
        self.last_error = None # Reset error
        try:
            summary, tree, content = gitingest.ingest(source=self.repo_source)
            self.summary = summary
            self.tree = tree
            self.content = content
            print(f"Successfully ingested: {self.repo_source}")
            return self._format_output(self.summary, self.tree, self.content)

        except Exception as e:
            self.last_error = (
                f"Error processing repository '{self.repo_source}':\\n"
                f"{type(e).__name__}: {e}\\n"
                # f"Traceback:\\n{traceback.format_exc()}" # Uncomment for debug
            )
            print(self.last_error)
            self.summary = self.tree = self.content = None # Clear on error
            return None

    def ingest_filtered(self, extra_excludes: Optional[Set[str]] = None) -> Optional[str]:
        """
        Ingests a **local directory**, excluding common non-code files
        and optionally provided extra patterns.

        Assumes `self.repo_source` points to an existing local directory.
        Applies default gitingest ignores, Python-specific exclusions
        (PYTHON_PROJECT_EXCLUDES), and any `extra_excludes`. Stores the
        filtered results in instance attributes.

        Args:
            extra_excludes: An optional set of additional glob patterns to exclude.

        Returns:
            A string containing the formatted summary, file tree, and content
            of the *filtered* repository directory, or None if an error occurred.
        """
        print(f"Attempting to ingest and filter local directory: {self.repo_source}")
        self.last_error = None # Reset error

        local_path = Path(self.repo_source).resolve()

        # --- Pre-check: Verify the path exists and is a directory ---
        if not local_path.exists():
            self.last_error = f"Error: Local path does not exist: {local_path}"
            print(self.last_error)
            return None
        if not local_path.is_dir():
            self.last_error = f"Error: Local path is not a directory: {local_path}"
            print(self.last_error)
            return None
        # -----------------------------------------------------------

        # Combine exclusion patterns
        combined_excludes = DEFAULT_IGNORE_PATTERNS.union(PYTHON_PROJECT_EXCLUDES)
        if extra_excludes:
            combined_excludes = combined_excludes.union(extra_excludes)
        # print(f"Applying {len(combined_excludes)} exclusion patterns.") # Optional debug

        try:
            summary, tree, content = gitingest.ingest(
                source=str(local_path),
                exclude_patterns=combined_excludes,
            )
            self.filtered_summary = summary
            self.filtered_tree = tree
            self.filtered_content = content
            print(f"Successfully ingested and filtered local directory: {local_path}")
            return self._format_output(self.filtered_summary, self.filtered_tree, self.filtered_content, filtered=True)

        except Exception as e:
            self.last_error = (
                f"Error processing filtered local directory '{local_path}':\\n"
                f"{type(e).__name__}: {e}\\n"
                # f"Traceback:\\n{traceback.format_exc()}" # Uncomment for debug
            )
            print(self.last_error)
            self.filtered_summary = self.filtered_tree = self.filtered_content = None # Clear on error
            return None
    
    def complete_task(self, task: str, model_name: str = "gemini-2.5-pro-preview-03-25") -> Optional[str]:
        """
        Uses a Gemini model to generate code and supporting actions for a given task,
        based on the ingested repository content.

        Prioritizes filtered content if available, otherwise uses standard content.

        Args:
            task: The task description to complete.
            model_name: The specific Gemini model to use (defaults to gemini-2.5-pro-exp-03-25).

        Returns:
            A string containing the model's response (code and actions),
            or None if no content is available or an error occurred during generation.
        """
        self.last_error = None # Reset error

        # 1. Select content (prioritize filtered)
        summary, tree, content, source_type = None, None, None, None
        if self.filtered_summary and self.filtered_tree and self.filtered_content:
            summary = self.filtered_summary
            tree = self.filtered_tree
            content = self.filtered_content
            source_type = "(Filtered)"
            print("Using filtered repository content for the task.")
        elif self.summary and self.tree and self.content:
            summary = self.summary
            tree = self.tree
            content = self.content
            source_type = ""
            print("Using standard repository content for the task.")
        else:
            self.last_error = "Error: No repository content has been successfully ingested yet."
            print(self.last_error)
            return None

        # 2. Construct the prompt
        prompt = f"""You are an expert AI programmer assistant. You are given the context of a code repository and a task to perform within that repository.

Repository Context:
--- Repository Summary {source_type} ---
{summary}

--- File Tree {source_type} ---
{tree}

--- File Contents {source_type} ---
{content}

Task:
{task}

Instructions:
Generate the response to fulfill the task based on the provided repository context using the {model_name} model.
Structure your response using the following format:

### answer:
[Provide your textual answer, explanation, or the primary code solution here.]

### actions:
[List all supporting actions needed to make the solution runnable. This includes file operations, shell commands, and environment setup.]

For file operations, use the following specific format:
<edit_file>
[path/to/file_name.ext]
<content>
[The complete new content for the file, or the specific code changes.]
</content>
</edit_file>

For shell commands, list them directly:
<run_shell>
[command_1]
[command_2]
</run_shell>

For dependencies, list the necessary packages or setup steps:
<install_dependency>
[e.g., pip install package_name==1.0.0]
</install_dependency>

Ensure the generated code within the answer or file content is complete and directly usable.
"""

        # 3. Call the Gemini API
        print(f"Sending task to Gemini model: {model_name}")
        try:
            client = genai.Client(api_key="AIzaSyDC9s0y58wQbQhNfRyxQBcaL5PByJK9saQ")

            # Prepare content for the API
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                    ],
                ),
            ]
            generate_content_config = types.GenerateContentConfig(
                response_mime_type="text/plain",
            )

            for chunk in client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=generate_content_config,
            ):
                print(chunk.text, end="")

            print("Successfully received response from Gemini.")

        except Exception as e:
            self.last_error = (
                f"Error during Gemini API call ({model_name}) for task '{task}':\n"
                f"{type(e).__name__}: {e}\n"
                # f"Traceback:\n{traceback.format_exc()}" # Uncomment for debug
            )
            print(self.last_error)
            return None

# --- Example Usage ---
if __name__ == "__main__":
    # Define the repo source (local path in this example)
    # repo_path = "https://github.com/some/repo.git" # Example URL
    repo_path = "/home/pvduy/duy/ii-agent" # Example local path
    repo_path = "/home/pvduy/duy/repos/ii-agent"
    #repo_path = "/home/pvduy/khoa/ii-agent/workspace/eb3a3d1c-2152-4129-8cc1-d2eb8ed1a183"
    # Create an agent instance
    agent = RepoAgent(repo_path)
    agent.ingest_filtered()
    import ipdb; ipdb.set_trace()
    result = agent.complete_task("""
I want to restructure the repo to this structure
ii_agent
src
    agents
        agent_base.py # agent_base
            # Tool 
        agent.py # seq_thinking
            # agent_base
        agent_codeact.py # ...

    tools
        files/
            edit_file.py # str_replace_tool
            write_file.py # file_write_tool
            browse_web.py # browser_use
            ...
        browser/
            ...
    llm
        anthropic.py
        openai.py
    utils.py

    prompts

cli.py
ws_server.py

frontend/
    index.html
can you help
""")
