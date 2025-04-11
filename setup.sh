#!/bin/bash
# Setup script for the project

current_dir=$(pwd)

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# reload uv
export PATH="$HOME/.local/bin:$PATH"

# Create virtual environment
echo "Creating virtual environment..."
uv venv

# Install dependencies
echo "Installing dependencies..."
uv pip install -r requirements.txt

# Install the package
echo "Installing package..."
uv pip install -e .

echo "Done installing packages for augment-swebench-agent"

### INSTALL SWE-BENCH EVALUATION TOOLS
echo "Installing SWE-bench evaluation tools..."
SWEBENCH_REF="006a760a95c9cc11e987884d7e311d74a16db88a"
(cd ${HOME} && python -m venv swebench_eval_tools_env)
git clone https://github.com/SWE-bench/SWE-bench.git ${HOME}/swebench
(source ${HOME}/swebench_eval_tools_env/bin/activate \
    && cd ${HOME}/swebench \
    && git apply ${current_dir}/swebench_patch.diff \
    && git checkout ${SWEBENCH_REF} \
    && pip install -e . \
    && deactivate)
echo "Done installing SWE-bench evaluation tools, including a separate virtual environment for SWE-bench at ${HOME}/swebench_eval_tools_env."

# navigate to cwd
cd ${current_dir}

# Install pre-commit hooks
echo "Installing pre-commit hooks..."
uv run pre-commit install-hooks

echo "Setup complete! Activate the virtual environment for augment-swebench-agent with:"
echo "source .venv/bin/activate"

echo "Package installed and virtual environment created."
