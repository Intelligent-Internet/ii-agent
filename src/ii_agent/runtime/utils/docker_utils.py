import socket
import importlib.metadata
from pathlib import Path
import subprocess

import docker


def get_project_root() -> Path:
    try:
        dist = importlib.metadata.distribution("ii-agent")
        if dist.files:
            package_location = Path(str(dist.locate_file("."))).resolve()
            while package_location.parent != package_location:
                if (package_location / "pyproject.toml").exists():
                    return package_location
                package_location = package_location.parent

        return package_location
    except Exception as e:
        raise Exception("Failed to get project root: " + str(e))


def get_host_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        raise Exception("Failed to get host IP: " + str(e))


def image_exists(client: docker.DockerClient, tag):
    try:
        client.images.get(tag)
        return True
    except Exception:
        return False


def build_if_not_exists(
    client: docker.DockerClient, path: str, dockerfile: str, tag: str
):
    if image_exists(client, tag):
        print(f"✓ Image {tag} already exists, skipping build")
        return client.images.get(tag)
    else:
        print(f"Building {tag}...")
        try:
            try:
                print(f"Building {tag} with docker client")
                subprocess.run(
                    f"cd {path} && docker build -t {tag} -f {dockerfile} .", shell=True
                )
                if image_exists(client, tag):
                    print(f"✓ Successfully built {tag}")
                    return client.images.get(tag)
                else:
                    raise Exception(f"Failed to build image {tag}")
            except Exception:
                print(
                    f"✗ Build failed for {tag}, trying to build with docker python sdk"
                )
                image, _ = client.images.build(
                    path=path, dockerfile=dockerfile, tag=tag, rm=True
                )
                if image_exists(client, tag):
                    print(f"✓ Successfully built {tag}")
                    return image
                else:
                    raise Exception(f"Failed to build image {tag}")
        except Exception as e:
            raise Exception(f"Failed to build image {tag}: {e}")
