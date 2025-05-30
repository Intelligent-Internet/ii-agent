# src/ii_agent/tools/video_generate_from_text_tool.py
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types

from google.cloud import storage
from google.auth.exceptions import DefaultCredentialsError

from ii_agent.tools.base import (
    MessageHistory,
    LLMTool,
    ToolImplOutput,
)
from ii_agent.utils import WorkspaceManager

GCP_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
GCP_LOCATION = os.environ.get("GOOGLE_CLOUD_REGION")
VEO_GCS_OUTPUT_BUCKET = os.environ.get("VEO_GCS_OUTPUT_BUCKET")


def _get_gcs_client():
    """Helper to get GCS client and handle potential auth errors."""
    try:
        # Attempt to create a client. This will use GOOGLE_APPLICATION_CREDENTIALS
        # or other ADC (Application Default Credentials) if set up.
        return storage.Client()
    except DefaultCredentialsError:
        print(
            "GCS Authentication Error: Could not find default credentials. "
            "Ensure GOOGLE_APPLICATION_CREDENTIALS is set or you are authenticated "
            "via `gcloud auth application-default login`."
        )
        raise
    except Exception as e:
        print(f"Unexpected error initializing GCS client: {e}")
        raise


def download_gcs_file(gcs_uri: str, destination_local_path: Path) -> None:
    """Downloads a file from GCS to a local path."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError("GCS URI must start with gs://")

    try:
        storage_client = _get_gcs_client()
        bucket_name, blob_name = gcs_uri.replace("gs://", "").split("/", 1)

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        destination_local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(destination_local_path))
        print(f"Successfully downloaded {gcs_uri} to {destination_local_path}")
    except Exception as e:
        print(f"Error downloading GCS file {gcs_uri}: {e}")
        raise


def upload_to_gcs(local_file_path: Path, gcs_destination_uri: str) -> None:
    """Uploads a local file to GCS."""
    if not gcs_destination_uri.startswith("gs://"):
        raise ValueError("GCS destination URI must start with gs://")
    if not local_file_path.exists() or not local_file_path.is_file():
        raise FileNotFoundError(f"Local file for upload not found: {local_file_path}")

    try:
        storage_client = _get_gcs_client()
        bucket_name, blob_name = gcs_destination_uri.replace("gs://", "").split("/", 1)

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(local_file_path))
        print(f"Successfully uploaded {local_file_path} to {gcs_destination_uri}")
    except Exception as e:
        print(f"Error uploading file to GCS {gcs_destination_uri}: {e}")
        raise


def delete_gcs_blob(gcs_uri: str) -> None:
    """Deletes a blob from GCS."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError("GCS URI must start with gs://")

    try:
        storage_client = _get_gcs_client()
        bucket_name, blob_name = gcs_uri.replace("gs://", "").split("/", 1)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if blob.exists():  # Check if blob exists before trying to delete
            blob.delete()
            print(f"Successfully deleted GCS blob: {gcs_uri}")
        else:
            print(f"GCS blob not found, skipping deletion: {gcs_uri}")
    except Exception as e:
        print(f"Error deleting GCS blob {gcs_uri}: {e}")


class VideoGenerateFromTextTool(LLMTool):
    name = "generate_video_from_text"
    description = """Generates a short video based on a text prompt only using Google's Veo 2 model.
The generated video will be saved to the specified local path in the workspace."""
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "A detailed description of the video to be generated.",
            },
            "output_filename": {
                "type": "string",
                "description": "The desired relative path for the output MP4 video file within the workspace (e.g., 'generated_videos/my_video.mp4'). Must end with .mp4.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16"],
                "default": "16:9",
                "description": "The aspect ratio for the generated video.",
            },
            "duration_seconds": {
                "type": "string",
                "enum": ["5", "6", "7", "8"],
                "default": "5",
                "description": "The duration of the video in seconds.",
            },
            "enhance_prompt": {
                "type": "boolean",
                "default": True,
                "description": "Whether to enhance the provided prompt for better results.",
            },
            "allow_person_generation": {
                "type": "boolean",
                "default": False,
                "description": "Set to true to allow generation of people (adults). If false, prompts with people may fail or generate abstract representations.",
            },
        },
        "required": ["prompt", "output_filename"],
    }

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        if not VEO_GCS_OUTPUT_BUCKET or not VEO_GCS_OUTPUT_BUCKET.startswith("gs://"):
            raise ValueError(
                "VEO_GCS_OUTPUT_BUCKET environment variable must be set to a valid GCS URI (e.g., gs://my-bucket-name)"
            )
        self.workspace_manager = workspace_manager
        if not GCP_PROJECT_ID:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")
        self.client = genai.Client(
            project=GCP_PROJECT_ID, location=GCP_LOCATION, vertexai=True
        )
        self.video_model = "veo-2.0-generate-001"  # As per the notebook

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        prompt = tool_input["prompt"]
        relative_output_filename = tool_input["output_filename"]
        aspect_ratio = tool_input.get("aspect_ratio", "16:9")
        duration_seconds = int(tool_input.get("duration_seconds", "5"))
        enhance_prompt = tool_input.get("enhance_prompt", True)
        allow_person = tool_input.get("allow_person_generation", False)

        person_generation_setting = "allow_adult" if allow_person else "dont_allow"

        if not relative_output_filename.lower().endswith(".mp4"):
            return ToolImplOutput(
                "Error: output_filename must end with .mp4",
                "Invalid output filename for video.",
                {"success": False, "error": "Output filename must be .mp4"},
            )

        local_output_path = self.workspace_manager.workspace_path(
            Path(relative_output_filename)
        )
        local_output_path.parent.mkdir(parents=True, exist_ok=True)

        # Veo outputs to GCS, so we need a unique GCS path for the intermediate file
        unique_gcs_filename = f"veo_temp_output_{uuid.uuid4().hex}.mp4"
        gcs_output_uri = f"{VEO_GCS_OUTPUT_BUCKET.rstrip('/')}/{unique_gcs_filename}"

        try:
            operation = self.client.models.generate_videos(
                model=self.video_model,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    output_gcs_uri=gcs_output_uri,  # Veo requires a GCS URI
                    number_of_videos=1,
                    duration_seconds=duration_seconds,
                    person_generation=person_generation_setting,
                    enhance_prompt=enhance_prompt,
                ),
            )

            # Poll for completion (as in the notebook)
            # Consider making this truly async in a real agent to not block the main thread
            # For now, we'll simulate with sleeps and checks.
            polling_interval_seconds = 15
            max_wait_time_seconds = 600  # 10 minutes
            elapsed_time = 0

            while not operation.done:
                if elapsed_time >= max_wait_time_seconds:
                    return ToolImplOutput(
                        f"Error: Video generation timed out after {max_wait_time_seconds} seconds for prompt: {prompt}",
                        "Video generation timed out.",
                        {"success": False, "error": "Timeout"},
                    )
                time.sleep(polling_interval_seconds)
                elapsed_time += polling_interval_seconds
                operation = self.client.operations.get(
                    operation
                )  # Refresh operation status
                # Optionally log operation.metadata or progress if available

            if operation.error:
                return ToolImplOutput(
                    f"Error generating video: {str(operation.error)}",
                    "Video generation failed.",
                    {"success": False, "error": str(operation.error)},
                )

            if not operation.response or not operation.result.generated_videos:
                return ToolImplOutput(
                    f"Video generation completed but no video was returned for prompt: {prompt}",
                    "No video returned from generation process.",
                    {"success": False, "error": "No video output from API"},
                )

            generated_video_gcs_uri = operation.result.generated_videos[0].video.uri

            # Download the video from GCS to the local workspace
            download_gcs_file(generated_video_gcs_uri, local_output_path)

            # Delete the temporary file from GCS
            delete_gcs_blob(generated_video_gcs_uri)

            output_url = (
                f"http://localhost:{self.workspace_manager.file_server_port}/workspace/{relative_output_filename}"
                if hasattr(self.workspace_manager, "file_server_port")
                else f"(Local path: {relative_output_filename})"
            )

            return ToolImplOutput(
                f"Successfully generated video from text and saved to '{relative_output_filename}'. Playback URL (if server running): {output_url}",
                f"Video generated and saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
                    "url": output_url,
                },
            )

        except Exception as e:
            return ToolImplOutput(
                f"Error generating video from text: {str(e)}",
                "Failed to generate video from text.",
                {"success": False, "error": str(e)},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Generating video from text prompt for file: {tool_input['output_filename']}"


SUPPORTED_IMAGE_FORMATS_MIMETYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class VideoGenerateFromImageTool(LLMTool):
    name = "generate_video_from_image"
    description = f"""Generates a short video by adding motion to an input image using Google's Veo 2 model.
Optionally, a text prompt can be provided to guide the motion.
The input image must be in the workspace. Supported image formats: {", ".join(SUPPORTED_IMAGE_FORMATS_MIMETYPE.keys())}.
The generated video will be saved to the specified local path in the workspace."""
    input_schema = {
        "type": "object",
        "properties": {
            "image_file_path": {
                "type": "string",
                "description": "The relative path to the input image file within the workspace (e.g., 'uploads/my_image.png').",
            },
            "output_filename": {
                "type": "string",
                "description": "The desired relative path for the output MP4 video file within the workspace (e.g., 'generated_videos/animated_image.mp4'). Must end with .mp4.",
            },
            "prompt": {
                "type": "string",
                "description": "(Optional) A text prompt to guide the motion and style of the video. If not provided, the model will add generic motion.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16"],
                "default": "16:9",
                "description": "The aspect ratio for the generated video. Should ideally match the input image.",
            },
            "duration_seconds": {
                "type": "string",
                "enum": ["5", "6", "7", "8"],
                "default": "5",
                "description": "The duration of the video in seconds.",
            },
            "allow_person_generation": {
                "type": "boolean",
                "default": False,
                "description": "Set to true to allow generation of people (adults) if the image contains them or the prompt implies them.",
            },
        },
        "required": ["image_file_path", "output_filename"],
    }

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.workspace_manager = workspace_manager
        if not GCP_PROJECT_ID:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")
        self.genai_client = genai.Client(
            project=GCP_PROJECT_ID, location="global", vertexai=True
        )
        self.video_model = "veo-2.0-generate-001"

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        relative_image_path = tool_input["image_file_path"]
        relative_output_filename = tool_input["output_filename"]
        prompt = tool_input.get("prompt")
        aspect_ratio = tool_input.get("aspect_ratio", "16:9")
        duration_seconds = int(tool_input.get("duration_seconds", "5"))
        allow_person = tool_input.get("allow_person_generation", False)

        person_generation_setting = "allow_adult" if allow_person else "dont_allow"

        if not relative_output_filename.lower().endswith(".mp4"):
            return ToolImplOutput(
                "Error: output_filename must end with .mp4",
                "Invalid output filename for video.",
                {"success": False, "error": "Output filename must be .mp4"},
            )

        local_input_image_path = self.workspace_manager.workspace_path(
            Path(relative_image_path)
        )
        local_output_video_path = self.workspace_manager.workspace_path(
            Path(relative_output_filename)
        )
        local_output_video_path.parent.mkdir(parents=True, exist_ok=True)

        if not local_input_image_path.exists() or not local_input_image_path.is_file():
            return ToolImplOutput(
                f"Error: Input image file not found at {relative_image_path}",
                f"Input image not found: {relative_image_path}",
                {"success": False, "error": "Input image file not found"},
            )
        image_suffix = local_input_image_path.suffix.lower()
        if image_suffix not in SUPPORTED_IMAGE_FORMATS_MIMETYPE:
            return ToolImplOutput(
                f"Error: Input image format {image_suffix} is not supported.",
                f"Unsupported input image format: {image_suffix}",
                {"success": False, "error": "Unsupported input image format"},
            )

        mime_type = SUPPORTED_IMAGE_FORMATS_MIMETYPE[image_suffix]

        temp_gcs_image_filename = f"veo_temp_input_{uuid.uuid4().hex}{image_suffix}"
        temp_gcs_image_uri = (
            f"{VEO_GCS_OUTPUT_BUCKET.rstrip('/')}/{temp_gcs_image_filename}"
        )

        generated_video_gcs_uri_for_cleanup = None  # For finally block

        try:
            upload_to_gcs(local_input_image_path, temp_gcs_image_uri)

            unique_gcs_video_filename = f"veo_temp_output_{uuid.uuid4().hex}.mp4"
            gcs_output_video_uri = (
                f"{VEO_GCS_OUTPUT_BUCKET.rstrip('/')}/{unique_gcs_video_filename}"
            )
            generated_video_gcs_uri_for_cleanup = gcs_output_video_uri

            generate_videos_kwargs = {
                "model": self.video_model,
                "image": types.Image(gcs_uri=temp_gcs_image_uri, mime_type=mime_type),
                "config": types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    output_gcs_uri=gcs_output_video_uri,
                    number_of_videos=1,
                    duration_seconds=duration_seconds,
                    person_generation=person_generation_setting,
                ),
            }
            if prompt:
                generate_videos_kwargs["prompt"] = prompt

            operation = self.genai_client.models.generate_videos(
                **generate_videos_kwargs
            )

            polling_interval_seconds = 15
            max_wait_time_seconds = 600
            elapsed_time = 0

            while not operation.done:
                if elapsed_time >= max_wait_time_seconds:
                    raise TimeoutError(
                        f"Video generation timed out after {max_wait_time_seconds} seconds."
                    )
                time.sleep(polling_interval_seconds)
                elapsed_time += polling_interval_seconds
                operation = self.genai_client.operations.get(
                    operation
                )  # Use self.genai_client

            if operation.error:
                raise Exception(
                    f"Video generation API error: {operation.error.message}"
                )

            if not operation.response or not operation.result.generated_videos:
                raise Exception("Video generation completed but no video was returned.")

            # The GCS URI of the *actual* generated video might differ slightly if Veo adds prefixes/folders
            actual_generated_video_gcs_uri = operation.result.generated_videos[
                0
            ].video.uri
            generated_video_gcs_uri_for_cleanup = (
                actual_generated_video_gcs_uri  # Update for accurate cleanup
            )

            download_gcs_file(actual_generated_video_gcs_uri, local_output_video_path)

            output_url = (
                f"http://localhost:{self.workspace_manager.file_server_port}/workspace/{relative_output_filename}"
                if hasattr(self.workspace_manager, "file_server_port")
                else f"(Local path: {relative_output_filename})"
            )

            return ToolImplOutput(
                f"Successfully generated video from image '{relative_image_path}' and saved to '{relative_output_filename}'. Playback URL (if server running): {output_url}",
                f"Video from image generated and saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
                    "url": output_url,
                },
            )

        except Exception as e:
            return ToolImplOutput(
                f"Error generating video from image: {str(e)}",
                "Failed to generate video from image.",
                {"success": False, "error": str(e)},
            )
        finally:
            # Clean up temporary GCS files
            if temp_gcs_image_uri:
                try:
                    delete_gcs_blob(temp_gcs_image_uri)
                except Exception as e_cleanup_img:
                    print(
                        f"Warning: Failed to clean up GCS input image {temp_gcs_image_uri}: {e_cleanup_img}"
                    )

            if (
                generated_video_gcs_uri_for_cleanup
            ):  # This will be the actual output URI from Veo
                try:
                    delete_gcs_blob(generated_video_gcs_uri_for_cleanup)
                except Exception as e_cleanup_vid:
                    print(
                        f"Warning: Failed to clean up GCS output video {generated_video_gcs_uri_for_cleanup}: {e_cleanup_vid}"
                    )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Generating video from image for file: {tool_input['output_filename']}"


if __name__ == "__main__":
    from ii_agent.utils import WorkspaceManager

    workspace_manager = WorkspaceManager(root="workspace")
    tool = VideoGenerateFromTextTool(workspace_manager)
    print(
        tool.run_impl(
            {
                "prompt": "A video of a cat playing with a ball",
                "output_filename": "cat_playing.mp4",
            }
        )
    )

    tool = VideoGenerateFromImageTool(workspace_manager)
    print(
        tool.run_impl(
            {"image_file_path": "bert.jpeg", "output_filename": "animated_image.mp4"}
        )
    )
