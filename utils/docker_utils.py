import docker
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

AUGMENT_ROOT = Path(__file__).parent.parent
MAX_DOCKER_CONCURRENCY = 4


def get_issue_image_name(problem_id: str, workspace: Path) -> str:
    """Fetch a docker image for the issue."""
    issue_key = problem_id.replace("__", "_1776_")
    return f"swebench/sweb.eval.x86_64.{issue_key}:latest"


def set_volume_permissions(container_id, volume_path: Path):
    # Make sure we can read the volume
    # Docker is running as root, we may be running as augment.
    my_uid = os.getuid()
    my_gid = os.getgid()
    logging.info(f"Fixing permissions for {volume_path} to {my_uid}:{my_gid}")
    env = os.environ.copy()
    try:
        subprocess.check_call(
            [
                "sudo",
                "chmod",
                "a+rx",
            ]
            + [p.as_posix() for p in volume_path.parents],
            env=env,
        )
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to chmod {volume_path}: {e}")
        raise
    # Change the owner to the current user
    try:
        container_out = subprocess.check_output(
            [
                "sudo",
                "chown",
                "-R",
                f"{my_uid}:{my_gid}",
                volume_path.as_posix(),
            ],
            env=env,
            text=True,
            errors="backslashreplace",
        )
        logging.debug(container_out)
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to chown {volume_path}: {e}")
        raise


def start_container(workspace: Path, problem_id: str, semaphore: Any) -> str:
    """Start a docker container for the issue."""
    stop_container(f"sweb.augment.{problem_id}")
    image_name = get_issue_image_name(problem_id, workspace)
    logging.info(f"Starting container for {problem_id}")
    client = docker.from_env()
    logging.info(f"Pulling image {image_name}")
    with semaphore:
        logging.info(f"Starting pull for {image_name}")
        client.images.pull(image_name)
        logging.info(f"Finished pulling image {image_name}")
    logging.info(f"Running docker run for {image_name} in {workspace}")

    with semaphore:
        logging.info(f"Starting run for {image_name}")
        container = client.containers.run(
            name=f"sweb.augment.{problem_id}_{uuid.uuid4().hex[:8]}",
            image=image_name,
            detach=True,
            volumes=["/testbed"],
            command="bash -c 'git config --global user.email a && git config --global user.name a && git config --global --add safe.directory /testbed && git commit --allow-empty -am augment && sleep 7200'",  # Time out and die, eventually, if we are interrupted
        )
        logging.info(f"Finished startup for {image_name}")
    # Give it a second to start
    time.sleep(10)
    container_id = container.id
    assert container_id is not None
    logging.info(f"Started {container_id} for {problem_id}")
    # Get the volume path from the container
    volume_info = container.attrs["Mounts"]
    volume_path = Path(volume_info[0]["Source"])
    (workspace / problem_id).unlink(missing_ok=True)
    (workspace / problem_id).symlink_to(volume_path)

    retry = True
    while True:
        try:
            set_volume_permissions(container_id, volume_path)
            break
        except Exception as e:
            logging.warning(f"Failed to set permissions: {e}")
            if not retry:
                # Don't fail for this, it may not be fatal.
                break
            retry = False
            time.sleep(10)
    return container_id


def remove_container_image(image_name: str) -> None:
    """Remove a docker image."""
    try:
        client = docker.from_env()
        client.images.remove(image=image_name, force=True)
        logging.info(f"Removed image {image_name}")
    except docker.errors.APIError as e:  # type: ignore
        logging.warning(f"Failed to remove image {image_name}: {e}")


def stop_container(container_id: str, remove_image: str = "") -> None:
    """Stop a docker container for the issue."""
    container = None
    try:
        client = docker.from_env()
        container = client.containers.get(container_id)
    except Exception as e:
        logging.info(f"Container {container_id} not found: {e}")

    if container:
        try:
            logging.info(f"Stopping container {container_id}")
            container.stop()
            logging.info(f"Stopped container {container_id}")
        except docker.errors.NotFound as e:  # type: ignore
            logging.warning(f"Failed to stop container {container_id}: {e}")
        except docker.errors.APIError as e:  # type: ignore
            logging.warning(f"Failed to stop container {container_id}: {e}")
        try:
            logging.info(f"Removing container {container_id}")
            container.remove()
            time.sleep(10)
            logging.info(f"Removed container {container_id}")
        except docker.errors.NotFound as e:  # type: ignore
            logging.warning(f"Failed to stop container {container_id}: {e}")
        except docker.errors.APIError as e:  # type: ignore
            logging.warning(f"Failed to stop container {container_id}: {e}")

    if remove_image:
        # Add a small delay to ensure container removal is complete
        time.sleep(5)
        remove_container_image(remove_image)


def setup_workspace(
    workspace: Path, problem_id: str, lock: Any, semaphore: Any
) -> Tuple[Dict[str, str], str]:
    """Setup the workspace for the agent."""
    env: Dict[str, str] = os.environ.copy()

    # Create a conda environment; we don't use it, but it protects the
    # agent's environment from changes.
    logging.debug(f"Creating conda enviroment in {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    # Multiple simultaneous conda installs are no good.
    with lock:
        subprocess.check_output(
            [
                "conda",
                "create",
                "-y",
                "-q",
                "-p",
                str(workspace / "conda_3.9"),
                "python==3.9",
            ]
        )

    env["ISSUE_ID"] = problem_id
    env["SWEBENCH_WORKSPACE"] = str(workspace)
    env["PATH"] = f"{workspace}/python_wrappers/bin:{workspace}/conda_3.9/bin" + (
        f":{env['PATH']}" if "PATH" in env else ""
    )
    env["PYTHONPATH"] = f"{AUGMENT_ROOT}" + (
        f":{env['PYTHONPATH']}" if "PYTHONPATH" in env else ""
    )
    for k, v in env.items():
        logging.debug(f"ENV {k}=={v}")

    # Copy the python wrapper into the workspace
    container_id = start_container(workspace, problem_id, semaphore)

    return env, container_id
