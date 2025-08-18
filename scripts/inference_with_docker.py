"""
Script for running ii-agent in a Docker container with MCP server support.
Please build the docker first by running
```bash
sudo docker build -f docker/backend/DockerfileBacEndOnly.dockerfile -t ii-agent-backend:0.2 .
```
# Create the venv env 
python3 -m venv .venv
source .venv/bin/activate

# Install ii_agent

pip install -e .
pip install datasets 
pip install docker

# Create the config file 
example in scripts/settings.json

# Run 
python3 scripts/inference_with_docker.py --query "create the simple calculator web project" --setting-path scripts/settings.json --workspace-path scripts/calculator_workspace --session-id trace_00
"""

import argparse
import asyncio
import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

import docker

from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.cli.state_persistence import StateManager
from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.state import State
from ii_agent.controller.tool_manager import AgentToolManager
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.core.logger import logger
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.llm import get_client
from ii_agent.llm.base import ToolParam
from ii_agent.llm.context_manager import LLMCompact
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.prompts import get_system_prompt
from ii_agent.utils.constants import TOKEN_BUDGET
from ii_tool.core import WorkspaceManager
from ii_tool.core.config import (
    WebSearchConfig,
    WebVisitConfig,
    FullStackDevConfig
)
from ii_tool.tools.agent import TaskAgentTool, TASK_AGENT_SYSTEM_PROMPT
from ii_tool.utils import load_tools_from_mcp


class IIAgentDockerManager:
    """Manager class for running ii-agent in Docker container."""
    
    def __init__(self, 
                 image_name: str = "ii-agent-backend:0.2",
                 container_name: str = "ii-agent-container",
                 output_dir: str = "./ii_agent_output"):
        """
        Initialize Docker manager for ii-agent.
        
        Args:
            image_name: Docker image name to use
            container_name: Name for the container
            output_dir: Directory to save extracted content
        """
        self.image_name = image_name
        self.container_name = container_name
        self.output_dir = Path(output_dir)
        self.client = None
        self.container = None
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            self.client = docker.from_env()
            logger.info("Successfully connected to Docker daemon")
        except Exception as e:
            logger.error(f"Failed to connect to Docker daemon: {e}")
            logger.error("Make sure Docker is installed and running")
            sys.exit(1)
    
    def pull_or_check_image(self) -> bool:
        """
        Check if image exists locally or pull it.
        
        Returns:
            True if image is available, False otherwise
        """
        try:
            image = self.client.images.get(self.image_name)
            logger.info(f"Image {self.image_name} found locally")
            return True
        except docker.errors.ImageNotFound:
            logger.warning(f"Image {self.image_name} not found locally")
            logger.error(f"Please ensure the image {self.image_name} is built")
            return False
    
    def start_container(self, 
                       command: Optional[str] = None,
                       environment: Optional[Dict[str, str]] = None,
                       volumes: Optional[Dict[str, Dict[str, str]]] = None,
                       ports: Optional[Dict[str, int]] = None) -> bool:
        """
        Start the ii-agent Docker container.
        
        Args:
            command: Command to run in container
            environment: Environment variables
            volumes: Volume mappings
            ports: Port mappings
            
        Returns:
            True if container started successfully
        """
        try:
            self.cleanup_container()
            
            logger.info(f"Starting container {self.container_name}...")
            
            container_config = {
                'image': self.image_name,
                'name': self.container_name,
                'detach': True,
                'tty': True,
                'stdin_open': True,
                'environment': environment or {},
                'volumes': volumes or {},
                'ports': ports or {},
            }
            
            if command:
                container_config['command'] = command
            
            self.container = self.client.containers.run(**container_config)
            logger.info(f"Container {self.container_name} started successfully")
            logger.info(f"Container ID: {self.container.short_id}")
            
            self.container.reload()
            if self.container.status != 'running':
                logger.error(f"Container exited with status: {self.container.status}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to start container: {e}")
            return False
    
    def run_command(self, command: str, workdir: str = "/workspace") -> tuple:
        """
        Execute a command inside the running container.
        
        Args:
            command: Command to execute
            workdir: Working directory in container
            
        Returns:
            Tuple of (exit_code, output)
        """
        if not self.container:
            logger.error("Container is not running")
            return (1, "")
        
        try:
            logger.info(f"Executing command: {command}")
            result = self.container.exec_run(
                command,
                workdir=workdir,
                tty=True,
                stdin=True
            )
            
            output = result.output.decode('utf-8') if result.output else ""
            logger.debug(f"Command output: {output}")
            
            return (result.exit_code, output)
            
        except Exception as e:
            logger.error(f"Failed to execute command: {e}")
            return (1, str(e))
    
    def run_command_background(self, command: str, workdir: str = "/workspace") -> str:
        """
        Execute a command in the background inside the running container.
        
        Args:
            command: Command to execute
            workdir: Working directory in container
            
        Returns:
            Execution ID for monitoring the background process
        """
        if not self.container:
            logger.error("Container is not running")
            return None
        
        try:
            logger.info(f"Executing background command: {command}")
            exec_result = self.container.exec_run(
                command,
                workdir=workdir,
                tty=True,
                stdin=True,
                detach=True
            )
            logger.info(f"Background command started with ID: {exec_result}")
            return exec_result
            
        except Exception as e:
            logger.error(f"Failed to execute background command: {e}")
            return None
    
    def check_background_process(self, exec_id: str) -> dict:
        """
        Check the status of a background process.
        
        Args:
            exec_id: Execution ID returned from run_command_background
            
        Returns:
            Dict with process status information
        """
        if not self.container:
            logger.error("Container is not running")
            return {"running": False, "exit_code": None}
        
        try:
            exec_instance = self.client.api.exec_inspect(exec_id)
            return {
                "running": exec_instance["Running"],
                "exit_code": exec_instance["ExitCode"]
            }
        except Exception as e:
            logger.error(f"Failed to check background process: {e}")
            return {"running": False, "exit_code": None}
    
    def stop_background_process(self, exec_id: str) -> bool:
        """
        Stop a background process by killing it.
        
        Args:
            exec_id: Execution ID of the background process
            
        Returns:
            True if successfully stopped
        """
        try:
            self.run_command(f"kill $(ps aux | grep {exec_id} | grep -v grep | awk '{{print $2}}')")
            logger.info(f"Sent stop signal to background process {exec_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop background process: {e}")
            return False
    
    def copy_from_container(self, container_path: str, host_path: str) -> bool:
        """
        Copy files from container to host.
        
        Args:
            container_path: Path inside container
            host_path: Destination path on host
            
        Returns:
            True if successful
        """
        if not self.container:
            logger.error("Container is not running")
            return False
        
        try:
            logger.info(f"Copying {container_path} from container to {host_path}")
            
            bits, stat = self.container.get_archive(container_path)
            
            host_path = Path(host_path)
            host_path.parent.mkdir(parents=True, exist_ok=True)
            
            tar_stream = io.BytesIO()
            for chunk in bits:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            with tarfile.open(fileobj=tar_stream) as tar:
                tar.extractall(path=host_path.parent)
            
            logger.info(f"Successfully copied files to {host_path}")
            return True
            
        except docker.errors.NotFound:
            logger.warning(f"Path {container_path} not found in container")
            return False
        except Exception as e:
            logger.error(f"Failed to copy from container: {e}")
            return False
    
    def copy_to_container(self, host_path: str, container_path: str) -> bool:
        """
        Copy files from host to container.
        
        Args:
            host_path: Path on host
            container_path: Destination path inside container
            
        Returns:
            True if successful
        """
        if not self.container:
            logger.error("Container is not running")
            return False
        
        try:
            host_path = Path(host_path)
            if not host_path.exists():
                logger.warning(f"Host path {host_path} does not exist")
                return False
                
            logger.info(f"Copying {host_path} from host to {container_path} in container")
            
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                tar.add(str(host_path), arcname=os.path.basename(host_path))
            
            tar_stream.seek(0)
            
            self.container.put_archive(
                path=os.path.dirname(container_path),
                data=tar_stream.getvalue()
            )
            
            logger.info(f"Successfully copied files to {container_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy to container: {e}")
            return False
    
    def extract_ii_agent_folder(self, container_path="/root/.ii_agent") -> bool:
        """
        Extract ~/.ii_agent folder from container to host.
        
        Returns:
            True if successful
        """
        host_path = self.output_dir
        os.makedirs(host_path, exist_ok=True)
        
        exit_code, output = self.run_command(f"ls -la {container_path}")
        
        if exit_code != 0:
            logger.warning(f"Folder {container_path} not found in container: {output}")
            logger.info("Attempting to initialize ii-agent...")
            self.run_command("ii-agent --version")
        
        success = self.copy_from_container(container_path, str(host_path))
        
        if success:
            logger.info(f"ii-agent data extracted to: {host_path}")
            self.list_extracted_files(host_path)
        
        return success
    
    def list_extracted_files(self, path: Path):
        """List extracted files for verification."""
        logger.info("\nExtracted files:")
        for root, dirs, files in os.walk(path):
            level = root.replace(str(path), '').count(os.sep)
            indent = ' ' * 2 * level
            logger.info(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                logger.info(f"{subindent}{file}")
    
    def get_container_logs(self) -> str:
        """Get container logs."""
        if not self.container:
            return ""
        
        try:
            logs = self.container.logs(tail=100).decode('utf-8')
            return logs
        except Exception as e:
            logger.error(f"Failed to get logs: {e}")
            return ""
    
    def cleanup_container(self):
        """Stop and remove container if it exists."""
        try:
            existing = self.client.containers.get(self.container_name)
            logger.info(f"Stopping existing container {self.container_name}...")
            existing.stop(timeout=10)
            existing.remove()
            logger.info(f"Removed container {self.container_name}")
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
    
    def run_ii_agent_task(self, task: str) -> str:
        """
        Run an ii-agent task in the container.
        
        Args:
            task: Task description for ii-agent
            
        Returns:
            Task output
        """
        logger.info(f"Running ii-agent task: {task}")
        
        task_file = "/tmp/task.txt"
        command = f'echo "{task}" > {task_file} && ii-agent --file {task_file}'
        
        exit_code, output = self.run_command(command)
        
        if exit_code == 0:
            logger.info("Task completed successfully")
        else:
            logger.error(f"Task failed with exit code {exit_code}")
        
        return output


class SimpleSubscriber:
    """Simple subscriber to capture agent output without rich console UI"""
    
    def __init__(self):
        self.messages = []
        
    async def on_event(self, event):
        """Handle events from the agent"""
        if hasattr(event, 'type'):
            event_type = event.type
            event_data = event.data if hasattr(event, 'data') else {}
        else:
            event_type = event.get("type")
            event_data = event.get("data", {})
            
        if event_type == "agent_message":
            content = event_data.get("content", "") if isinstance(event_data, dict) else str(event_data)
            self.messages.append(content)
            print(f"Agent: {content}")
        elif event_type == "tool_execution":
            tool_name = event_data.get("name", "") if isinstance(event_data, dict) else ""
            print(f"Executing tool: {tool_name}")
        elif event_type == "error":
            error = event_data.get("error", "") if isinstance(event_data, dict) else str(event_data)
            print(f"Error: {error}")


async def async_predict(
    query: str,
    workspace_path: str = "workspace",
    session_id: str = "test_predict",
    local_file_storage: str = "workspace/.ii_agent/",
    continue_from_state: bool = False,
    setting_path: str = None,
    port_mcp: int = 7009,
    image_name: str = 'ii-agent-backend:0.2',
    keep_running_docker: bool=False
) -> str:
    """
    Execute a query using ii-agent without the CLI interface.
    
    Args:
        query: The user query to process
        workspace_path: Path to the workspace directory
        session_id: Unique session identifier
        local_file_storage: Path to local storage for ii-agent files
        continue_from_state: Whether to continue from previous state
        setting_path: Path to settings JSON file
        port_mcp: Port for MCP server
        image_name: Docker image name
        
    Returns:
        The agent's response as a string
    """
    
    mcp_config = {
        "mcpServers": {
            "fast_mcp": {
                "transport": "http",
                "url": f"http://localhost:{port_mcp}/mcp/",
                "headers": {"Authorization": "Bearer token"},
                "auth": "bearer"
            }
        }
    }
    
    custom_container_name = f"mcp-{session_id}-{int(time.time())}"
    manager = IIAgentDockerManager(
        image_name=image_name,
        container_name=f"ii-agent-container-{custom_container_name}",
        output_dir="./ii_agent_output",
    )
    
    port_mapping = {f"{port_mcp}/tcp": port_mcp}
    volume_mapping = {
        os.path.abspath(workspace_path): {"bind": "/app/workspace_docker_mcp", "mode": "rw"}
    }
    
    if not manager.start_container(
        command=None,
        ports=port_mapping,
        volumes=volume_mapping,
        environment={"PYTHONUNBUFFERED": "1"}
    ):
        logger.error("Failed to start container")
        sys.exit(1)
        
    try:
        command = f'python3 src/ii_tool/mcp/server.py --workspace_dir workspace_docker_mcp --session_id {session_id} --port {port_mcp}'
        exec_id = manager.run_command_background(command, workdir="/app")
        print(exec_id)
        
        logger.info("Waiting for MCP server to start...")
        await asyncio.sleep(5)
        
        process_status = manager.check_background_process(exec_id)
        if not process_status["running"] and process_status["exit_code"] is not None:
            logger.error(f"MCP server failed to start. Exit code: {process_status['exit_code']}")
            manager.cleanup_container()
            sys.exit(1)

        config = IIAgentConfig(session_id=session_id, mcp_config=mcp_config, file_store_path=local_file_storage)
        
        print(local_file_storage)
        if not os.path.exists(os.path.join(local_file_storage, "settings.json")):
            assert setting_path is not None
            settings = json.loads(setting_path)
            with open(os.path.join(local_file_storage, "settings.json"), "w+") as f:
                f.write(json.dumps(settings))
                
        settings_store = await FileSettingsStore.get_instance(config=config, user_id=None)
        settings = await settings_store.load()
        
        if not settings or not settings.llm_configs or not settings.llm_configs.get('default'):
            raise RuntimeError(
                "No configuration found. Please run 'ii-agent-cli' first to set up your configuration."
            )
        
        default_llm_config = settings.llm_configs.get('default')
        
        if isinstance(default_llm_config, dict):
            llm_config = LLMConfig(
                provider=default_llm_config.get('provider'),
                model=default_llm_config.get('model'),
                api_key=default_llm_config.get('api_key'),
                base_url=default_llm_config.get('base_url'),
                temperature=default_llm_config.get('temperature', 0.7),
                max_tokens=default_llm_config.get('max_tokens', 32768),
            )
        else:
            llm_config = default_llm_config
        
        workspace_manager = WorkspaceManager(Path(workspace_path))
        
        event_stream = AsyncEventStream()
        subscriber = SimpleSubscriber()
        event_stream.subscribe(subscriber.on_event)
        
        state_manager = StateManager(
            Path(workspace_path), 
            continue_session=continue_from_state, 
            session_id=session_id, 
            local_file_storage=local_file_storage
        )
        
        saved_state_data = None
        if continue_from_state:
            saved_state_data = state_manager.load_state()
            if saved_state_data:
                print("🔄 Continuing from previous state...")
            else:
                print("⚠️ No saved state found, starting fresh...")
        
        llm_client = get_client(llm_config)
        
        agent_config = AgentConfig(
            max_tokens_per_turn=config.max_output_tokens_per_turn,
            system_prompt=get_system_prompt('/app/workspace_docker_mcp'),
        )
        
        tool_manager = AgentToolManager()
        
        web_search_config = WebSearchConfig()
        web_visit_config = WebVisitConfig()
        fullstack_dev_config = FullStackDevConfig()
        
        image_search_config = None
        video_generate_config = None
        image_generate_config = None
        
        if config.mcp_config:
            mcp_tools = await load_tools_from_mcp(config.mcp_config)
            tool_manager.register_tools(mcp_tools)
        
        task_agent_config = AgentConfig(
            max_tokens_per_turn=config.max_output_tokens_per_turn,
            system_prompt=TASK_AGENT_SYSTEM_PROMPT,
        )
        
        tools = [ToolParam(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema
        ) for tool in tool_manager.get_tools()]
        
        agent = FunctionCallAgent(
            llm=llm_client,
            config=agent_config,
            tools=[
                ToolParam(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema
                ) for tool in tool_manager.get_tools()
            ]
        )
        
        token_counter = TokenCounter()
        context_manager = LLMCompact(
            client=llm_client,
            token_counter=token_counter,
            token_budget=TOKEN_BUDGET,
        )
        
        if saved_state_data:
            from ii_agent.cli.state_persistence import restore_agent_state
            state = restore_agent_state(saved_state_data)
        else:
            state = State()
            
        config.allow_tools = set(
            [i.name for i in tool_manager.get_tools()]
        )
        
        agent_controller = AgentController(
            agent=agent,
            tool_manager=tool_manager,
            init_history=state,
            workspace_manager=workspace_manager,
            event_stream=event_stream,
            context_manager=context_manager,
            interactive_mode=False,
            config=config,
        )
        
        system_prompt = agent_config.system_prompt
        with open(os.path.join(workspace_path, ".ii_agent", "other_config.json"), "w+") as f:
            f.write(json.dumps({
                "system_prompt": system_prompt,
                "tools": [i.model_dump(mode='json') for i in agent.tools]
            }))
            
        print(f"\n📋 Processing query: {query}\n")
        print(f"🗂️ Workspace: {workspace_manager.get_workspace_path()}")
        print(f"🤖 Model: {llm_config.model}")
        print("-" * 50)
        
        try:
            response = await agent_controller.run_agent_async(instruction=query)
            
            state_manager.save_state(
                agent_controller.history_global,
                config,
                llm_config,
                workspace_path
            )
            
            print("-" * 50)
            print("✅ Query executed successfully")
            
            if hasattr(response, 'llm_content'):
                return response.llm_content
            elif hasattr(response, 'user_display_content'):
                return response.user_display_content
            else:
                return str(response)
            
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            print(f"\n❌ Error: {e}")
            raise
    finally:
        if keep_running_docker is False:
            manager.cleanup_container()


async def main():
    """Main function with example usage"""
    parser = argparse.ArgumentParser(
        description="Run ii-agent in Docker container"
    )
    parser.add_argument(
        "--query",
        default="Create a simple fibonacci program",
        help="Query to II-agent"
    )
    parser.add_argument(
        "--workspace-path",
        default="workspace_predict/test_query_HA",
        help="Workspace directory path"
    )
    parser.add_argument(
        "--session-id",
        default="test_query_HA",
        help="Session ID for ii-agent"
    )
    parser.add_argument(
        "--setting-path",
        default="scripts/settings.json",
        help="Path to settings JSON file"
    )
    parser.add_argument(
        "--setting-json",
        default=None,
        help="Settings as JSON string"
    )
    parser.add_argument(
        "--keep-running-docker",
        default=False,
        help="Keep running docker to check the output agent (i.e web running,...)"
    )
    parser.add_argument(
        "--image-name",
        default="ii-agent-backend:0.2"
    )
    args = parser.parse_args()
    
    os.makedirs(args.workspace_path, exist_ok=True)
    os.makedirs(os.path.join(args.workspace_path, ".ii_agent"), exist_ok=True)

    if args.setting_json is not None:
        config_json = json.loads(args.setting_json)
    else:
        config_json = json.load(open(args.setting_path))
        
    with open(os.path.join(args.workspace_path, ".ii_agent", "settings.json"), "w+") as f:
        f.write(json.dumps(config_json))

    query = args.query
    
    try:
        response = await async_predict(
            query=query,
            workspace_path=args.workspace_path,
            session_id=args.session_id,
            local_file_storage=os.path.join(args.workspace_path, ".ii_agent"),
            continue_from_state=False,
            image_name=args.image_name,
            keep_running_docker=args.keep_running_docker
        )
        
        print(f"\n📝 Final Response:\n{response}")
        
    except Exception as e:
        print(f"\n❌ Failed to execute query: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())