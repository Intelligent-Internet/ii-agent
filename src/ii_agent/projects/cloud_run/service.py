"""Cloud Run Publisher Service.

This module provides functionality to deploy user applications to Google Cloud Run.
It handles:
- Downloading source code from sandboxes
- Uploading source to Cloud Storage
- Building container images via Cloud Build (with pre-built base images for speed)
- Deploying to Cloud Run
- Managing custom domains (optional, via Cloudflare)
"""

from __future__ import annotations

import asyncio
import io
import re
import time
import tarfile
from pathlib import Path
from typing import Callable

from ii_agent.projects.cloud_run.schemas import (
    CloudRunConfig,
    DeploymentResult,
    DeploymentStatus,
    TemplateType,
)
from ii_agent.projects.cloud_run.templates import TEMPLATE_PORTS
from ii_agent.projects.cloud_run.source_preparer import (
    detect_template_type,
    prepare_source_with_dockerfile,
)
from ii_agent.core.logger import logger


class CloudRunPublisher:
    """Publisher service for deploying applications to Cloud Run."""

    # Directories and files to exclude from source upload
    EXCLUDE_PATTERNS = {
        "node_modules",
        ".git",
        ".next",
        "__pycache__",
        ".venv",
        "venv",
        ".env.local",
        ".env.development.local",
        ".env.test.local",
        ".env.production.local",
        "*.pyc",
        ".DS_Store",
        "dist",
        "build",
        ".cache",
        "coverage",
        ".nyc_output",
    }

    def __init__(
        self,
        config: CloudRunConfig,
        on_status_update: Callable[[DeploymentStatus, str], None] | None = None,
    ):
        """Initialize the Cloud Run publisher.

        Args:
            config: Cloud Run configuration
            on_status_update: Optional callback for status updates
        """
        self.config = config
        self.on_status_update = on_status_update

        # Lazy load clients to avoid import errors when GCP libraries not installed
        self._storage_client = None
        self._build_client = None
        self._run_client = None

    @property
    def storage_client(self):
        """Lazy-loaded Cloud Storage client.

        Note: Cloud Storage doesn't have an official async client,
        so we use the sync client with run_in_executor for I/O operations.
        """
        if self._storage_client is None:
            from google.cloud import storage

            self._storage_client = storage.Client(project=self.config.project_id)
        return self._storage_client

    @property
    def build_client(self):
        """Lazy-loaded Cloud Build async client."""
        if self._build_client is None:
            from google.cloud.devtools import cloudbuild_v1

            self._build_client = cloudbuild_v1.CloudBuildAsyncClient()
        return self._build_client

    @property
    def run_client(self):
        """Lazy-loaded Cloud Run async client."""
        if self._run_client is None:
            from google.cloud import run_v2

            self._run_client = run_v2.ServicesAsyncClient()
        return self._run_client

    async def publish(
        self,
        source_bytes: bytes,
        service_name: str,
        env_vars: dict[str, str] | None = None,
    ) -> DeploymentResult:
        """Deploy source code to Cloud Run.

        Args:
            source_bytes: Tar.gz bytes of the source code
            service_name: Name for the Cloud Run service (must be DNS-compatible)
            env_vars: Optional environment variables to set

        Returns:
            DeploymentResult with the deployment outcome
        """
        service_name = self._sanitize_service_name(service_name)

        try:
            # 0. Detect template type from source
            template_type = await detect_template_type(source_bytes)
            logger.info(f"Detected template type: {template_type.value}")

            # 1. Prepare source with Dockerfile
            self._update_status(DeploymentStatus.UPLOADING, "Preparing source code...")
            prepared_source = await prepare_source_with_dockerfile(source_bytes, template_type)

            # 2. Upload source to Cloud Storage
            self._update_status(DeploymentStatus.UPLOADING, "Uploading source code...")
            gcs_object = await self._upload_source(prepared_source, service_name)

            # 3. Build container image
            self._update_status(
                DeploymentStatus.BUILDING, "Building container image (ETA 1-2 mins)..."
            )
            build_result = await self._build_image(gcs_object, service_name, template_type)
            image_url = build_result["image_url"]

            # 4. Deploy to Cloud Run
            self._update_status(DeploymentStatus.DEPLOYING, "Deploying to Cloud Run (ETA 30s)...")
            port = TEMPLATE_PORTS.get(template_type, 3000)
            url = await self._deploy_service(service_name, image_url, env_vars, port)

            self._update_status(DeploymentStatus.COMPLETED, f"Deployed to {url}")

            return DeploymentResult(
                success=True,
                url=url,
                service_name=service_name,
                source_bucket=self.config.source_bucket,
                source_object=gcs_object,
                image_url=image_url,
                image_digest=build_result.get("image_digest"),
                build_id=build_result.get("build_id"),
                build_duration_ms=build_result.get("build_duration_ms"),
            )

        except Exception as e:
            logger.exception("Failed to deploy to Cloud Run")
            self._update_status(DeploymentStatus.FAILED, str(e))
            return DeploymentResult(
                success=False,
                error=str(e),
                service_name=service_name,
            )

    async def publish_from_directory(
        self,
        source_dir: Path,
        service_name: str,
        env_vars: dict[str, str] | None = None,
    ) -> DeploymentResult:
        """Deploy from a local directory.

        Args:
            source_dir: Path to the source directory
            service_name: Name for the Cloud Run service
            env_vars: Optional environment variables

        Returns:
            DeploymentResult with the deployment outcome
        """
        # Create tarball
        tar_bytes = await self._create_tarball(source_dir)
        return await self.publish(tar_bytes, service_name, env_vars)

    async def delete_service(self, service_name: str) -> bool:
        """Delete a Cloud Run service.

        Args:
            service_name: Name of the service to delete

        Returns:
            True if deleted successfully
        """
        from google.api_core.exceptions import NotFound

        try:
            service_name = self._sanitize_service_name(service_name)
            name = f"projects/{self.config.project_id}/locations/{self.config.region}/services/{service_name}"

            operation = await self.run_client.delete_service(name=name)
            await operation.result(timeout=300)

            logger.info(f"Deleted Cloud Run service: {service_name}")
            return True

        except NotFound:
            logger.warning(f"Service not found: {service_name}")
            return True
        except Exception:
            logger.exception(f"Failed to delete service: {service_name}")
            raise

    async def get_service_url(self, service_name: str) -> str | None:
        """Get the URL of a deployed service.

        Args:
            service_name: Name of the service

        Returns:
            Service URL or None if not found
        """
        from google.api_core.exceptions import NotFound

        try:
            service_name = self._sanitize_service_name(service_name)
            name = f"projects/{self.config.project_id}/locations/{self.config.region}/services/{service_name}"

            service = await self.run_client.get_service(name=name)

            return service.uri

        except NotFound:
            return None

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _update_status(self, status: DeploymentStatus, message: str) -> None:
        """Update deployment status via callback."""
        logger.info(f"Deployment status: {status.value} - {message}")
        if self.on_status_update:
            self.on_status_update(status, message)

    def _sanitize_service_name(self, name: str) -> str:
        """Sanitize service name for Cloud Run compatibility.

        Cloud Run requires:
        - Lowercase letters, numbers, and hyphens
        - Must start with a letter
        - Max 63 characters
        """
        # Convert to lowercase and replace invalid chars with hyphens
        sanitized = re.sub(r"[^a-z0-9-]", "-", name.lower())
        # Remove consecutive hyphens
        sanitized = re.sub(r"-+", "-", sanitized)
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip("-")
        # Ensure starts with letter
        if sanitized and not sanitized[0].isalpha():
            sanitized = "app-" + sanitized
        # Truncate to 63 chars
        sanitized = sanitized[:63].rstrip("-")

        return sanitized or "app"

    async def _create_tarball(self, source_dir: Path) -> bytes:
        """Create a tar.gz archive of the source directory."""

        def _should_exclude(path: Path, source_dir: Path) -> bool:
            """Check if path should be excluded."""
            rel_path = path.relative_to(source_dir)
            parts = rel_path.parts

            for part in parts:
                if part in self.EXCLUDE_PATTERNS:
                    return True
                for pattern in self.EXCLUDE_PATTERNS:
                    if "*" in pattern and part.endswith(pattern.lstrip("*")):
                        return True
            return False

        def _create_tar():
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
                for file_path in source_dir.rglob("*"):
                    if file_path.is_file() and not _should_exclude(file_path, source_dir):
                        arcname = file_path.relative_to(source_dir)
                        tar.add(file_path, arcname=arcname)
            return buffer.getvalue()

        return await asyncio.to_thread(_create_tar)

    async def _upload_source(self, source_bytes: bytes, service_name: str) -> str:
        """Upload source tarball to Cloud Storage."""
        bucket = self.storage_client.bucket(self.config.source_bucket)
        blob_name = f"{service_name}/source.tar.gz"
        blob = bucket.blob(blob_name)

        def _upload():
            blob.upload_from_string(source_bytes, content_type="application/gzip")

        await asyncio.to_thread(_upload)

        logger.info(f"Uploaded source to gs://{self.config.source_bucket}/{blob_name}")
        return blob_name

    async def _build_image(
        self, gcs_object: str, service_name: str, template_type: TemplateType
    ) -> str:
        """Build container image using BuildKit for faster builds.

        BuildKit provides significant performance improvements over buildpacks:
        - 40-60% faster builds due to parallel stage execution
        - Better layer caching with cache mounts
        - Support for prebuilt base images with dependencies pre-installed
        """
        from google.cloud.devtools import cloudbuild_v1

        image_url = f"{self.config.artifact_registry}/{service_name}:latest"

        # Get prebuilt base image for this template type (if available)
        base_image = self.config.base_images.get(template_type.value, "node:20-slim")

        # Build arguments for passing base image to Dockerfile
        build_args = [f"BASE_IMAGE={base_image}"]

        # Prepare BuildKit build steps
        # Using Cloud Build with BuildKit for better caching and parallel execution
        if template_type == TemplateType.UNKNOWN:
            # Fallback to buildpacks for unknown templates
            build_steps = [
                cloudbuild_v1.BuildStep(
                    name="gcr.io/k8s-skaffold/pack",
                    args=[
                        "build",
                        image_url,
                        "--builder",
                        "gcr.io/buildpacks/builder:google-22",
                        "--publish",
                    ],
                ),
            ]
            logger.info(f"Using buildpacks for unknown template: {service_name}")
        else:
            # Use BuildKit for known templates - much faster with prebuilt base images
            docker_build_args = []
            for arg in build_args:
                docker_build_args.extend(["--build-arg", arg])

            # Cache image URL for this service
            cache_image = f"{self.config.artifact_registry}/{service_name}:cache"

            build_steps = [
                # Step 1: Pull base image to warm up cache (runs in parallel with source extraction)
                cloudbuild_v1.BuildStep(
                    name="gcr.io/cloud-builders/docker",
                    args=["pull", base_image],
                    id="pull-base",
                ),
                # Step 2: Pull previous build cache (ignore errors if not exists)
                cloudbuild_v1.BuildStep(
                    name="gcr.io/cloud-builders/docker",
                    entrypoint="bash",
                    args=["-c", f"docker pull {cache_image} || true"],
                    id="pull-cache",
                ),
                # Step 3: Build with BuildKit using cached layers
                cloudbuild_v1.BuildStep(
                    name="gcr.io/cloud-builders/docker",
                    entrypoint="bash",
                    args=[
                        "-c",
                        f"""
                        # Build with BuildKit and layer caching
                        docker build \
                            --progress=plain \
                            {" ".join(docker_build_args)} \
                            --cache-from {base_image} \
                            --cache-from {cache_image} \
                            -t {image_url} \
                            -t {cache_image} \
                            .
                        """,
                    ],
                    env=["DOCKER_BUILDKIT=1"],
                    wait_for=["pull-base", "pull-cache"],
                    id="build",
                ),
                # Step 4: Push both the image and cache tag
                cloudbuild_v1.BuildStep(
                    name="gcr.io/cloud-builders/docker",
                    args=["push", "--all-tags", f"{self.config.artifact_registry}/{service_name}"],
                    wait_for=["build"],
                    id="push",
                ),
            ]
            logger.info(f"Using BuildKit with base image {base_image} for {service_name}")

        build = cloudbuild_v1.Build(
            source=cloudbuild_v1.Source(
                storage_source=cloudbuild_v1.StorageSource(
                    bucket=self.config.source_bucket,
                    object_=gcs_object,
                )
            ),
            steps=build_steps,
            options=cloudbuild_v1.BuildOptions(
                logging=cloudbuild_v1.BuildOptions.LoggingMode.CLOUD_LOGGING_ONLY,
                machine_type=cloudbuild_v1.BuildOptions.MachineType.E2_HIGHCPU_8,
            ),
            timeout={"seconds": 900},  # 15 minute timeout (faster with BuildKit)
        )

        operation = await self.build_client.create_build(
            project_id=self.config.project_id,
            build=build,
        )

        logger.info(f"Started Cloud Build (BuildKit) for {service_name}")

        build_start = time.time()

        result = await operation.result(timeout=900)

        build_duration_ms = int((time.time() - build_start) * 1000)

        if result.status != cloudbuild_v1.Build.Status.SUCCESS:
            raise RuntimeError(
                f"Build failed with status {result.status.name}: {result.status_detail}"
            )

        logger.info(f"Build completed: {image_url} (took {build_duration_ms}ms)")

        # Return dict with all build info
        return {
            "image_url": image_url,
            "build_id": result.id,
            "image_digest": "",
            "build_duration_ms": build_duration_ms,
        }

    async def _deploy_service(
        self,
        service_name: str,
        image_url: str,
        env_vars: dict[str, str] | None = None,
        port: int = 3000,
    ) -> str:
        """Deploy container to Cloud Run."""
        from google.api_core.exceptions import NotFound
        from google.cloud import run_v2

        parent = f"projects/{self.config.project_id}/locations/{self.config.region}"
        service_path = f"{parent}/services/{service_name}"

        # Build environment variables list
        env_list = []
        if env_vars:
            env_list = [run_v2.EnvVar(name=k, value=v) for k, v in env_vars.items()]

        # Use timestamp annotation to force Cloud Run to pull fresh image on each deploy
        deploy_timestamp = str(int(time.time()))

        service = run_v2.Service(
            template=run_v2.RevisionTemplate(
                annotations={
                    "deploy-timestamp": deploy_timestamp,
                },
                containers=[
                    run_v2.Container(
                        image=image_url,
                        ports=[run_v2.ContainerPort(container_port=port)],
                        resources=run_v2.ResourceRequirements(
                            limits={
                                "memory": self.config.memory,
                                "cpu": self.config.cpu,
                            },
                        ),
                        env=env_list,
                    )
                ],
                scaling=run_v2.RevisionScaling(
                    min_instance_count=self.config.min_instances,
                    max_instance_count=self.config.max_instances,
                ),
                timeout={"seconds": self.config.timeout_seconds},
                max_instance_request_concurrency=self.config.concurrency,
            ),
        )

        # Check if service exists
        try:
            existing = await self.run_client.get_service(name=service_path)
            # Update existing service
            service.name = service_path
            operation = await self.run_client.update_service(service=service)
            logger.info(f"Updating existing service: {service_name}")
        except NotFound:
            # Create new service
            operation = await self.run_client.create_service(
                parent=parent,
                service=service,
                service_id=service_name,
            )
            logger.info(f"Creating new service: {service_name}")

        # Wait for deployment
        result = await operation.result(timeout=600)

        # Make service publicly accessible
        await self._allow_unauthenticated_access(service_path)

        logger.info(f"Deployed service: {result.uri}")
        return result.uri

    async def _allow_unauthenticated_access(self, service_path: str) -> None:
        """Allow unauthenticated (public) access to the service."""
        from google.iam.v1 import policy_pb2

        policy = policy_pb2.Policy(
            bindings=[
                policy_pb2.Binding(
                    role="roles/run.invoker",
                    members=["allUsers"],
                )
            ]
        )

        await self.run_client.set_iam_policy(request={"resource": service_path, "policy": policy})
        logger.info("Enabled public access for service")


# Convenience function for quick deployments
async def deploy_to_cloud_run(
    source_bytes: bytes,
    service_name: str,
    env_vars: dict[str, str] | None = None,
    on_status_update: Callable[[DeploymentStatus, str], None] | None = None,
) -> DeploymentResult:
    """Convenience function to deploy to Cloud Run.

    Args:
        source_bytes: Tar.gz bytes of the source code
        service_name: Name for the Cloud Run service
        env_vars: Optional environment variables
        on_status_update: Optional callback for status updates

    Returns:
        DeploymentResult with the deployment outcome
    """
    config = CloudRunConfig.from_env()
    publisher = CloudRunPublisher(config, on_status_update)
    return await publisher.publish(source_bytes, service_name, env_vars)
