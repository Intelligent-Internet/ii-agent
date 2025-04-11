# Augment SWE-bench Verified Agent

[SWE-bench Verified](https://www.swebench.com/) tests how well AI systems handle software engineering tasks pulled from actual GitHub issues in popular open-source projects. Some example problems can be found in OpenAI’s [original blog post on the benchmark](https://openai.com/index/introducing-swe-bench-verified/). Where most coding benchmarks focus on isolated Leetcode-style programming problems, SWE-bench involves codebase navigation, iterating against a suite of regression tests, and overall much more complexity.

To achieve a 65.4% success rate on our first-ever SWE-bench submission we combined Claude Sonnet 3.7 as our core driver, along with OpenAI’s o1 as our ensembler. We deferred leveraging our own models to build a strong open-source baseline agent with off-the-shelf models.

Since Anthropic's models are currently state-of-the-art on code, we used Claude Sonnet 3.7 as our agent's core driver, and we forked our agent system architecture from [Anthropic's own blog post about SWE-bench](https://www.anthropic.com/news/claude-3-7-sonnet).

## Features

- Small and simple coding agent implementation + SWE-bench docker harness that is super easy to run and build on top of.
- Implementation of tools from our SWE-bench submission:
  - Bash command execution
  - File viewing and editing
  - Sequential thinking for complex problem-solving
- Prompt template + system prompt from our SWE-bench submission.
- Integration with Anthropic's Claude for core agent and OpenAI models for ensembling
- Command approval management for safe execution
- Majority vote ensembler for selecting the best solution from multiple candidates
- Support for running agent in a Docker container
- Support for running SWE-bench eval harness

## Installation

### Prerequisites

- [Docker](https://www.docker.com/) (We tested with `Docker version 26.1.3, build 26.1.3-0ubuntu1~22.04.1`.)
- Anthropic API key (for Claude models)
- OpenAI API key (for OpenAI models)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/augmentcode/augment-swebench-agent.git
   cd augment-swebench-agent
   ```

2. Install dependencies:
   ```bash
   ./setup.sh
   source .venv/bin/activate
   ```

3. Set your API keys:
   ```bash
   # For Anthropic Claude models
   export ANTHROPIC_API_KEY=your_anthropic_api_key_here

   # For OpenAI models
   export OPENAI_API_KEY=your_openai_api_key_here
   ```

## Ways to use this repo

- Interactive mode: Use `cli.py` to spin up an interactive agent for experimentation or as a personal coding assistant!
- SWE-bench mode: Use `run_agent_on_swebench_problem.py` to run the agent on SWE-bench problems. This is similar to the script we used to generate our SWE-bench submission.

More details on both below!

## Usage (interactive mode)

Run the CLI interface to interact with the agent directly. By default, the agent will run
in the current directory.

```bash
python cli.py
```

This will start an interactive session where you can communicate with the agent and assign it tasks.

### Command-line Options

- `--workspace`: Path to the workspace directory (default: current directory)
- `--problem-statement`: Provide a problem statement to make the agent non-interactive (default: None)
- `--needs-permission`: Whether to require permission before executing commands (default: False)
- `--use-container-workspace`: Path to the shared volume that is mounted into the Docker container. This must be set if you are using `--docker-container-id`. (default: None)
- `--docker-container-id`: ID of the Docker container to use. This must be set if you are using `--use-container-workspace`. (default: None)

Example:
```bash
python cli.py --workspace /path/to/project --problem-statement "Fix the login issue"
```

### Non-interactive Mode

You can run the agent in non-interactive mode by providing a problem statement:

```bash
python cli.py --problem-statement "Implement a feature to sort items by date"
```

### Using Docker

If you want to use a Docker container for the workspace, you need to specify the path to the Docker container
volume as well as the Docker container ID:

```bash
python cli.py --use-container-workspace --docker-container-id <container_id> --workspace /path/to/docker/volume
```

## Usage (SWE-bench mode)

### Quick Test Run

As a test run, run the following. It will generate 2 candidate solutions for each of 5 problems. It will also run the evaluation step for each candidate solution. Finally, it will provide instructions for how to run ensembler on the results.
```bash
python run_agent_on_swebench_problem.py --num-examples 5 --num-candidate-solutions 2
```

You can increase `--num-examples` and `--num-candidate-solutions` to run on more problems and generate more candidate solutions. But be aware that this will take longer and cost more money.

### Command-line Options

- `--num-examples`: Number of examples to run on (default: None, which runs on all examples)
- `--shard-ct`: Number of shards to split the work into (default: 1)
- `--shard-id`: Shard ID to run (0-indexed, default: 0)
- `--num-processes`: Number of processes to use for each example (default: 8)
- `--num-candidate-solutions`: Number of candidate solutions to generate for each example (default: 8)

### Running on more examples.

There are 500 examples total in SWE-bench Verified. Note that this can take awhile, so there are a few levels of parallelism this repository supports.
- Firstly, we suggest running 8 processes. This is the `--num-processes` flag. Beyond this, Docker hits issues.
- Secondly, we support a notion of breaking up the dataset into shards. This is the `--shard-ct` and `--shard-id` flags. This makes it relatively easy to split up the work across multiple machines, which circumnvents the issues with scaling Docker byeond 8 processes.

In our experiments, it took us a couple hours to run the full evaluation for 1 candidate solution per problem. This was
with 10 shards split out across separate pods (managed by Kubernetes) and each pod had 8 processes.

Keep in mind that you hit may hit rate-limits from Anthropic running 80 agents in parallel like we did. We have very high rate-limits with Anthropic's API that you may not have. Given this, you may have to run with a smaller `--shard-ct` and/or `--num-processes`.

Suppose you want to run with 10 shards and 8 processes per shard, then that would mean you run the following command 10 times, varying the `--shard-id` flag from 0 to 9, on 10 different machines:
```bash
python run_agent_on_swebench_problem.py --shard-ct 10 --shard-id <worker_index> > logs.out 2> logs.err
```

### Majority Vote Ensembler

The Majority Vote Ensembler is a tool that helps select the best solution from multiple candidates using an LLM. It works by presenting multiple candidate solutions to a problem to OpenAI's o1 model and asking it to analyze and select the most common solution.

#### How It Works

1. The tool takes a JSON file containing problems, each with multiple candidate solutions (diffs)
2. For each problem, it constructs a prompt using the `build_ensembler_prompt` function
3. The prompt is sent to o1.
4. The LLM analyzes all candidate solutions and selects the best one
5. The tool extracts the selected solution index from the LLM's response
6. Results are saved to a JSON file

#### Usage

```bash
python majority_vote_ensembler.py path/to/input.jsonl --output_path path/to/output.json --workers 8
```

Where:
- `path/to/input.jsonl` is a JSONL file containing problems and candidate solutions (see `example_ensembler_dataset.jsonl` for format)
- `--output_path` specifies where to save the results
- `--workers` sets the number of worker threads for parallel processing (default: 8)

#### Example

```bash
python majority_vote_ensembler.py example_ensembler_data.jsonl --output_path example_ensembler_results.json
```

#### Input Format

The input JSONL file should contain a list of problem objects, each with the following structure. The `diffs` are the candidate solutions generated by the agent. The `eval_outcomes` are the results of running the eval harness on each candidate solution, where the index corresponds to the index in the `diffs` array.

```json
{
  "id": "problem-1",
  "instruction": "Add a function to calculate factorial",
  "diffs": [
    "```diff\n@@ -10,3 +10,10 @@\n def function():\n     return x\n+\n+def new_function():\n+    return y\n```",
    "...other candidate solutions..."
  ],
  "eval_outcomes": [
    {
      "is_success": true
    },
    {
      "is_success": false
    },
    {
      "is_success": true
    }
  ]
}
```

#### Output Format

The output JSON file will contain an array of result objects, each with the following structure:

```json
[
  {
    "id": "problem-1",
    "instruction": "Add a function to calculate factorial",
    "response": "[LLM's full response text]",
    "selected_diff_index": 2,
    "selected_diff": "[The selected diff content]",
    "is_eval_success": true
  }
]
```

## Development

### Running Tests

```bash
pytest
```

### Adding New Tools

To add a new tool to the agent:

1. Create a new tool class in the `tools/` directory
2. Implement the required methods (run_impl, get_tool_param, etc.)
3. Add the tool to the agent's tools list in `tools/agent.py`

### Customizing the Agent Prompts

The agent's prompts are defined in the `prompts/` directory. You can customize the prompts by modifying the template strings in the respective files.

### Customizing the Majority Vote Ensembler

You can customize the Majority Vote Ensembler by modifying:

- `prompts/ensembler_prompt.py`: Change the prompt template used for ensembling
- Change the LLM model by modifying the `get_client` call in `process_problem` function

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License.
