# src/ii_agent/tools/video_generate_from_text_tool.py
import time
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types

try:
    from google.cloud import storage
    from google.auth.exceptions import DefaultCredentialsError

    HAS_GCS = True
except ImportError:
    HAS_GCS = False

from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.core import WorkspaceManager
from ii_tool.core.config import VideoGenerateConfig

DEFAULT_MODEL = "veo-2.0-generate-001"

# Google AI Studio person generation mapping
GENAI_PERSON_GENERATION_MAP = {
    "allow_adult": "allow_adult",
    "dont_allow": "dont_allow",
    "allow_all": "allow_all",
}


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


def _download_gcs_file(gcs_uri: str, destination_local_path: Path) -> None:
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


def _upload_to_gcs(local_file_path: Path, gcs_destination_uri: str) -> None:
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


def _delete_gcs_blob(gcs_uri: str) -> None:
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


class VideoGenerateFromTextTool(BaseTool):
    name = "generate_video_from_text"
    display_name = "Generate Video"
    description = """Generates a short video based on a text prompt using Google's Veo 2 model via Vertex AI or Google AI Studio.
The generated video will be saved to the specified local path in the workspace.
Uses Google AI Studio if GEMINI_API_KEY is set, otherwise falls back to Vertex AI if configured."""
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
    read_only = True

    def __init__(
        self, workspace_manager: WorkspaceManager, settings: VideoGenerateConfig
    ):
        print(settings)
        super().__init__()
        self.workspace_manager = workspace_manager

        # Extract configuration from settings
        gcp_project_id = None
        gcp_location = None
        gcs_output_bucket = None
        google_ai_studio_api_key = None

        gcp_project_id = settings.gcp_project_id
        gcp_location = settings.gcp_location
        gcs_output_bucket = settings.gcs_output_bucket
        google_ai_studio_api_key = settings.google_ai_studio_api_key

        if google_ai_studio_api_key:
            self.client = genai.Client(
                api_key=google_ai_studio_api_key,
                http_options={"api_version": "v1beta"},
            )
            self.api_type = "genai"
        elif gcp_project_id and gcp_location and gcs_output_bucket:
            if not gcs_output_bucket.startswith("gs://"):
                raise ValueError(
                    "GCS output bucket must be a valid GCS URI (e.g., gs://my-bucket-name)"
                )
            self.gcs_output_bucket = gcs_output_bucket
            self.client = genai.Client(
                project=gcp_project_id, location=gcp_location, vertexai=True
            )
            self.api_type = "vertex"
        else:
            raise ValueError(
                "Either Google AI Studio API key or GCP project ID, location, and GCS bucket must be provided in settings.media_config"
            )
        self.video_model = DEFAULT_MODEL

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        prompt = tool_input["prompt"]
        relative_output_filename = tool_input["output_filename"]
        aspect_ratio = tool_input.get("aspect_ratio", "16:9")
        duration_seconds = int(tool_input.get("duration_seconds", "5"))
        enhance_prompt = tool_input.get("enhance_prompt", True)
        allow_person = tool_input.get("allow_person_generation", False)

        person_generation_setting = "allow_adult" if allow_person else "dont_allow"

        if not relative_output_filename.lower().endswith(".mp4"):
            return ToolResult(
                llm_content="Error: output_filename must end with .mp4",
                user_display_content="Invalid output filename for video.",
                is_error=True,
            )

        local_output_path = Path(relative_output_filename).resolve()
        local_output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if self.api_type == "genai":
                # Google AI Studio API
                video_config = types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    number_of_videos=1,
                    duration_seconds=duration_seconds,
                    person_generation=person_generation_setting,
                )
                operation = self.client.models.generate_videos(
                    model=self.video_model,
                    prompt=prompt,
                    config=video_config,
                )
            else:  # vertex AI
                unique_gcs_filename = f"veo_temp_output_{uuid.uuid4().hex}.mp4"
                gcs_output_uri = (
                    f"{self.gcs_output_bucket.rstrip('/')}/{unique_gcs_filename}"
                )

                video_config = types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    output_gcs_uri=gcs_output_uri,
                    number_of_videos=1,
                    duration_seconds=duration_seconds,
                    person_generation=person_generation_setting,
                )
                operation = self.client.models.generate_videos(
                    model=self.video_model,
                    prompt=prompt,
                    config=video_config,
                )
            polling_interval_seconds = 15
            max_wait_time_seconds = 600
            elapsed_time = 0
            while not operation.done:
                if elapsed_time >= max_wait_time_seconds:
                    return ToolResult(
                        llm_content=f"Error: Video generation timed out after {max_wait_time_seconds} seconds for prompt: {prompt}",
                        user_display_content="Video generation timed out.",
                        is_error=True,
                    )
                time.sleep(polling_interval_seconds)
                elapsed_time += polling_interval_seconds
                operation = self.client.operations.get(operation)
            if operation.error:
                return ToolResult(
                    llm_content=f"Error generating video: {str(operation.error)}",
                    user_display_content="Video generation failed.",
                    is_error=True,
                )
            if not operation.response or not operation.result.generated_videos:
                return ToolResult(
                    llm_content=f"Video generation completed but no video was returned for prompt: {prompt}",
                    user_display_content="No video returned from generation process.",
                    is_error=True,
                )

            if self.api_type == "genai":
                generated_video = operation.result.generated_videos[0]
                self.client.files.download(file=generated_video.video)
                generated_video.video.save(str(local_output_path))
            else:  # vertex AI
                generated_video_gcs_uri = operation.result.generated_videos[0].video.uri
                _download_gcs_file(generated_video_gcs_uri, local_output_path)
                _delete_gcs_blob(generated_video_gcs_uri)

            return ToolResult(
                llm_content=f"Successfully generated video from text and saved to '{relative_output_filename}'",
                user_display_content=f"Video generated and saved to {relative_output_filename}",
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error generating video from text: {str(e)}",
                user_display_content="Failed to generate video from text.",
                is_error=True,
            )

    async def execute_mcp_wrapper(self, 
        prompt: str, 
        output_filename: str, 
        aspect_ratio: str = "16:9", 
        duration_seconds: int = 5, 
        enhance_prompt: bool = True, 
        allow_person_generation: bool = False
    ) -> str:        
        return await self._mcp_wrapper(
            tool_input={
                "prompt": prompt,
                "output_filename": output_filename,
                "aspect_ratio": aspect_ratio,
                "duration_seconds": duration_seconds,
                "enhance_prompt": enhance_prompt,
                "allow_person_generation": allow_person_generation,
            }
        )


SUPPORTED_IMAGE_FORMATS_MIMETYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class VideoGenerateFromImageTool(BaseTool):
    name = "generate_video_from_image"
    display_name = "Generate Video from Image"
    description = f"""Generates a short video by adding motion to an input image using Google's Veo 2 model via Vertex AI or Google AI Studio.
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
    read_only = True

    def __init__(
        self, workspace_manager: WorkspaceManager, settings: VideoGenerateConfig
    ):
        super().__init__()
        self.workspace_manager = workspace_manager

        gcp_project_id = settings.gcp_project_id
        gcp_location = settings.gcp_location
        gcs_output_bucket = settings.gcs_output_bucket
        google_ai_studio_api_key = settings.google_ai_studio_api_key

        if google_ai_studio_api_key:
            self.genai_client = genai.Client(
                api_key=google_ai_studio_api_key,
                http_options={"api_version": "v1beta"},
            )
            self.client = self.genai_client
            self.api_type = "genai"
        elif gcp_project_id and gcp_location and gcs_output_bucket:
            if not gcs_output_bucket.startswith("gs://"):
                raise ValueError(
                    "GCS output bucket must be a valid GCS URI (e.g., gs://my-bucket-name)"
                )
            self.gcs_output_bucket = gcs_output_bucket
            self.client = genai.Client(
                project=gcp_project_id, location=gcp_location, vertexai=True
            )
            self.api_type = "vertex"
        else:
            raise ValueError(
                "Either Google AI Studio API key or GCP project ID and location must be provided in settings.media_config"
            )
        self.video_model = DEFAULT_MODEL

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        relative_image_path = tool_input["image_file_path"]
        relative_output_filename = tool_input["output_filename"]
        prompt = tool_input.get("prompt")
        aspect_ratio = tool_input.get("aspect_ratio", "16:9")
        duration_seconds = int(tool_input.get("duration_seconds", "5"))
        allow_person = tool_input.get("allow_person_generation", False)

        person_generation_setting = "allow_adult" if allow_person else "dont_allow"

        if not relative_output_filename.lower().endswith(".mp4"):
            return ToolResult(
                llm_content="Error: output_filename must end with .mp4",
                user_display_content="Invalid output filename for video.",
                is_error=True,
            )

        local_input_image_path = Path(relative_image_path).resolve()
        local_output_video_path = Path(relative_output_filename).resolve()
        local_output_video_path.parent.mkdir(parents=True, exist_ok=True)

        if not local_input_image_path.exists() or not local_input_image_path.is_file():
            return ToolResult(
                llm_content=f"Error: Input image file not found at {relative_image_path}",
                user_display_content=f"Input image not found: {relative_image_path}",
                is_error=True,
            )
        image_suffix = local_input_image_path.suffix.lower()
        if image_suffix not in SUPPORTED_IMAGE_FORMATS_MIMETYPE:
            return ToolResult(
                llm_content=f"Error: Input image format {image_suffix} is not supported.",
                user_display_content=f"Unsupported input image format: {image_suffix}",
                is_error=True,
            )

        mime_type = SUPPORTED_IMAGE_FORMATS_MIMETYPE[image_suffix]

        try:
            if self.api_type == "genai":
                # Google AI Studio - use image bytes directly
                with open(local_input_image_path, "rb") as f:
                    image_bytes = f.read()

                generate_videos_kwargs = {
                    "model": self.video_model,
                    "image": types.Image(image_bytes=image_bytes, mime_type=mime_type),
                    "config": types.GenerateVideosConfig(
                        # person_generation is not allowed for image-to-video generation in Google AI Studio
                        aspect_ratio=aspect_ratio,
                        number_of_videos=1,
                        duration_seconds=duration_seconds,
                    ),
                }
            else:  # vertex AI
                temp_gcs_image_filename = (
                    f"veo_temp_input_{uuid.uuid4().hex}{image_suffix}"
                )
                temp_gcs_image_uri = (
                    f"{self.gcs_output_bucket.rstrip('/')}/{temp_gcs_image_filename}"
                )
                _upload_to_gcs(local_input_image_path, temp_gcs_image_uri)
                unique_gcs_video_filename = f"veo_temp_output_{uuid.uuid4().hex}.mp4"
                gcs_output_video_uri = (
                    f"{self.gcs_output_bucket.rstrip('/')}/{unique_gcs_video_filename}"
                )
                generated_video_gcs_uri_for_cleanup = gcs_output_video_uri

                generate_videos_kwargs = {
                    "model": self.video_model,
                    "image": types.Image(
                        gcs_uri=temp_gcs_image_uri, mime_type=mime_type
                    ),
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

            if self.api_type == "genai":
                operation = self.genai_client.models.generate_videos(
                    **generate_videos_kwargs
                )
            else:
                operation = self.client.models.generate_videos(**generate_videos_kwargs)

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
                if self.api_type == "genai":
                    operation = self.genai_client.operations.get(operation)
                else:
                    operation = self.client.operations.get(operation)

            if operation.error:
                raise Exception(
                    f"Video generation API error: {operation.error.message}"
                )

            if not operation.response or not operation.result.generated_videos:
                raise Exception("Video generation completed but no video was returned.")

            if self.api_type == "genai":
                generated_video = operation.result.generated_videos[0]
                self.genai_client.files.download(file=generated_video.video)
                generated_video.video.save(str(local_output_video_path))
            else:  # vertex AI
                actual_generated_video_gcs_uri = operation.result.generated_videos[
                    0
                ].video.uri
                generated_video_gcs_uri_for_cleanup = actual_generated_video_gcs_uri
                _download_gcs_file(
                    actual_generated_video_gcs_uri, local_output_video_path
                )

            return ToolResult(
                llm_content=f"Successfully generated video from image '{relative_image_path}' and saved to '{relative_output_filename}'.",
                user_display_content=f"Video from image generated and saved to {relative_output_filename}",
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                llm_content=f"Error generating video from image: {str(e)}",
                user_display_content="Failed to generate video from image.",
                is_error=True,
            )
        finally:
            # Clean up temporary files
            if self.api_type == "vertex" and temp_gcs_image_uri:
                try:
                    _delete_gcs_blob(temp_gcs_image_uri)
                except Exception as e_cleanup_img:
                    print(
                        f"Warning: Failed to clean up GCS input image {temp_gcs_image_uri}: {e_cleanup_img}"
                    )

            if self.api_type == "vertex" and generated_video_gcs_uri_for_cleanup:
                # This will be the actual output URI from Veo
                try:
                    _delete_gcs_blob(generated_video_gcs_uri_for_cleanup)
                except Exception as e_cleanup_vid:
                    print(
                        f"Warning: Failed to clean up GCS output video {generated_video_gcs_uri_for_cleanup}: {e_cleanup_vid}"
                    )

    async def execute_mcp_wrapper(self, 
        image_file_path: str, 
        output_filename: str, 
        prompt: str = None, 
        aspect_ratio: str = "16:9", 
        duration_seconds: int = 5, 
        allow_person_generation: bool = False
    ) -> str:        
        return await self._mcp_wrapper(
            tool_input={
                "image_file_path": image_file_path,
                "output_filename": output_filename,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration_seconds": duration_seconds,
                "allow_person_generation": allow_person_generation,
            }
        )

class LongVideoGenerateFromTextTool(BaseTool):
    name = "generate_long_video_from_text"
    display_name = "Generate Long Video"
    description = """Generates a long video (>= 10 seconds) based on a sequence of text prompts. Each prompt presents a new scene in the video, each scene is minimum 5 and maximum 8 seconds (preferably 5 seconds). Video is combined sequentially from the first scene to the last.
The generated video will be saved to the specified local path in the workspace."""
    input_schema = {
        "type": "object",
        "properties": {
            "prompts": {
                "type": "array",
                "items": {
                    "type": "string",
                    "description": "A description of a scene in the video.",
                },
                "description": "A sequence of detailed descriptions of the video to be generated. Each prompt presents a scene in the video.",
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
                "description": "The total duration of the video will be the sum of the duration of all scenes. The duration of each scene is determined by the model.",
            },
            "enhance_prompt": {
                "type": "boolean",
                "default": True,
                "description": "Whether to enhance the provided prompt for better results.",
            },
        },
        "required": ["prompts", "output_filename", "duration_seconds"],
    }
    read_only = True

    def __init__(
        self, workspace_manager: WorkspaceManager, settings: VideoGenerateConfig
    ):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.settings = settings

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        prompts = tool_input["prompts"]
        relative_output_filename = tool_input["output_filename"]
        aspect_ratio = tool_input.get("aspect_ratio", "16:9")
        duration_seconds = int(tool_input["duration_seconds"])
        enhance_prompt = tool_input.get("enhance_prompt", True)

        if not relative_output_filename.lower().endswith(".mp4"):
            return ToolResult(
                llm_content="Error: output_filename must end with .mp4",
                user_display_content="Invalid output filename for video.",
                is_error=True,
            )

        if len(prompts) == 0:
            return ToolResult(
                llm_content="Error: At least one prompt is required",
                user_display_content="No prompts provided for video generation.",
                is_error=True,
            )

        local_output_path = self.workspace_manager.workspace_path(
            Path(relative_output_filename)
        )
        local_output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temporary directory for scene videos and frames
        temp_dir = local_output_path.parent / f"temp_{uuid.uuid4().hex}"
        temp_dir.mkdir(exist_ok=True)

        scene_video_paths = []

        try:
            # Calculate duration per scene
            duration_per_scene = max(5, duration_seconds // len(prompts))
            if duration_per_scene > 8:
                duration_per_scene = 8

            # Generate first scene from text
            first_scene_filename = "scene_0.mp4"
            first_scene_path = temp_dir / first_scene_filename

            text_tool = VideoGenerateFromTextTool(self.workspace_manager, self.settings)
            first_scene_result = await text_tool.run_impl(
                {
                    "prompt": prompts[0],
                    "output_filename": str(
                        first_scene_path.relative_to(
                            self.workspace_manager.workspace_path(Path())
                        )
                    ),
                    "aspect_ratio": aspect_ratio,
                    "duration_seconds": str(duration_per_scene),
                    "enhance_prompt": enhance_prompt,
                    "allow_person_generation": True,
                }
            )

            if not first_scene_result.auxiliary_data.get("success", False):
                return ToolResult(
                    llm_content=f"Error generating first scene: {first_scene_result.auxiliary_data.get('error', 'Unknown error')}",
                    user_display_content="Failed to generate first scene.",
                    is_error=True,
                )

            scene_video_paths.append(first_scene_path)

            # Generate subsequent scenes from last frame + prompt
            image_tool = VideoGenerateFromImageTool(
                self.workspace_manager, self.settings
            )

            for i, prompt in enumerate(prompts[1:], 1):
                # Extract last frame from previous scene
                prev_video_path = scene_video_paths[-1]
                last_frame_path = temp_dir / f"last_frame_{i - 1}.png"

                # Use ffmpeg to extract last frame
                extract_cmd = [
                    "ffmpeg",
                    "-i",
                    str(prev_video_path),
                    "-vf",
                    "select=eq(n\\,0)",
                    "-q:v",
                    "3",
                    "-vframes",
                    "1",
                    "-f",
                    "image2",
                    str(last_frame_path),
                    "-y",
                ]

                # Actually extract the very last frame
                extract_cmd = [
                    "ffmpeg",
                    "-sseof",
                    "-1",
                    "-i",
                    str(prev_video_path),
                    "-update",
                    "1",
                    "-q:v",
                    "1",
                    str(last_frame_path),
                    "-y",
                ]

                subprocess.run(extract_cmd, check=True, capture_output=True)

                # Generate next scene from last frame + prompt
                scene_filename = f"scene_{i}.mp4"
                scene_path = temp_dir / scene_filename

                scene_result = await image_tool.run_impl(
                    {
                        "image_file_path": str(
                            last_frame_path.relative_to(
                                self.workspace_manager.workspace_path(Path())
                            )
                        ),
                        "output_filename": str(
                            scene_path.relative_to(
                                self.workspace_manager.workspace_path(Path())
                            )
                        ),
                        "prompt": prompt,
                        "aspect_ratio": aspect_ratio,
                        "duration_seconds": str(duration_per_scene),
                        "allow_person_generation": True,
                    }
                )

                if not scene_result.auxiliary_data.get("success", False):
                    return ToolResult(
                        llm_content=f"Error generating scene {i}: {scene_result.auxiliary_data.get('error', 'Unknown error')}",
                        user_display_content=f"Failed to generate scene {i}.",
                        is_error=True,
                    )

                scene_video_paths.append(scene_path)

            # Combine all scenes into final video
            if len(scene_video_paths) == 1:
                # Only one scene, just copy it
                shutil.copy2(scene_video_paths[0], local_output_path)
            else:
                # Create file list for ffmpeg concat
                concat_file = temp_dir / "concat_list.txt"
                with open(concat_file, "w") as f:
                    for video_path in scene_video_paths:
                        f.write(f"file '{video_path.absolute()}'\n")

                # Concatenate videos
                concat_cmd = [
                    "ffmpeg",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_file),
                    "-c",
                    "copy",
                    str(local_output_path),
                    "-y",
                ]

                subprocess.run(concat_cmd, check=True, capture_output=True)

            return ToolResult(
                llm_content=f"Successfully generated long video with {len(prompts)} scenes and saved to '{relative_output_filename}'",
                user_display_content=f"Long video with {len(prompts)} scenes generated and saved to {relative_output_filename}",
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                llm_content=f"Error generating long video: {str(e)}",
                user_display_content="Failed to generate long video.",
                is_error=True,
            )
        finally:
            # Clean up temporary files
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e_cleanup:
                    print(
                        f"Warning: Failed to clean up temporary directory {temp_dir}: {e_cleanup}"
                    )

    async def execute_mcp_wrapper(self, 
        prompts: list[str], 
        output_filename: str, 
        aspect_ratio: str = "16:9", 
        duration_seconds: int = 5, 
        enhance_prompt: bool = True
    ) -> str:        
        return await self._mcp_wrapper(
            tool_input={
                "prompts": prompts,
                "output_filename": output_filename,
                "aspect_ratio": aspect_ratio,
                "duration_seconds": duration_seconds,
                "enhance_prompt": enhance_prompt,
            }
        )

class LongVideoGenerateFromImageTool(BaseTool):
    name = "generate_long_video_from_image"
    display_name = "Generate Long Video from Image"
    description = """Generates a long video (>= 10 seconds) based on input image and a sequence of text prompts. Each prompt presents a new scene in the video, each scene is minimum 5 and maximum 8 seconds (preferably 5 seconds). Video is combined sequentially from the first scene to the last.
The generated video will be saved to the specified local path in the workspace."""
    input_schema = {
        "type": "object",
        "properties": {
            "image_file_path": {
                "type": "string",
                "description": "The relative path to the input image file within the workspace (e.g., 'uploads/my_image.png').",
            },
            "prompts": {
                "type": "array",
                "items": {
                    "type": "string",
                    "description": "A description of a scene in the video.",
                },
                "description": "A sequence of detailed descriptions of the video to be generated. Each prompt presents a scene in the video.",
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
                "description": "The total duration of the video will be the sum of the duration of all scenes. The duration of each scene is determined by the model.",
            },
            "enhance_prompt": {
                "type": "boolean",
                "default": True,
                "description": "Whether to enhance the provided prompt for better results.",
            },
        },
        "required": [
            "image_file_path",
            "prompts",
            "output_filename",
            "duration_seconds",
        ],
    }
    read_only = True

    def __init__(
        self, workspace_manager: WorkspaceManager, settings: VideoGenerateConfig
    ):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.settings = settings

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        image_file_path = tool_input["image_file_path"]
        prompts = tool_input["prompts"]
        relative_output_filename = tool_input["output_filename"]
        aspect_ratio = tool_input.get("aspect_ratio", "16:9")
        duration_seconds = int(tool_input["duration_seconds"])
        enhance_prompt = tool_input.get("enhance_prompt", True)

        if not relative_output_filename.lower().endswith(".mp4"):
            return ToolResult(
                llm_content="Error: output_filename must end with .mp4",
                user_display_content="Invalid output filename for video.",
                is_error=True,
            )

        if len(prompts) == 0:
            return ToolResult(
                llm_content="Error: At least one prompt is required",
                user_display_content="No prompts provided for video generation.",
                is_error=True,
            )

        local_output_path = self.workspace_manager.workspace_path(
            Path(relative_output_filename)
        )
        local_output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temporary directory for scene videos and frames
        temp_dir = local_output_path.parent / f"temp_{uuid.uuid4().hex}"
        temp_dir.mkdir(exist_ok=True)

        scene_video_paths = []

        try:
            # Calculate duration per scene
            duration_per_scene = max(5, duration_seconds // len(prompts))
            if duration_per_scene > 8:
                duration_per_scene = 8

            # Generate first scene from text
            first_scene_filename = "scene_0.mp4"
            first_scene_path = temp_dir / first_scene_filename

            image_tool = VideoGenerateFromImageTool(
                self.workspace_manager, self.settings
            )
            first_scene_result = await image_tool.run_impl(
                {
                    "image_file_path": image_file_path,
                    "prompt": prompts[0],
                    "output_filename": str(
                        first_scene_path.relative_to(
                            self.workspace_manager.workspace_path(Path())
                        )
                    ),
                    "aspect_ratio": aspect_ratio,
                    "duration_seconds": str(duration_per_scene),
                    "enhance_prompt": enhance_prompt,
                    "allow_person_generation": True,
                }
            )

            if not first_scene_result.auxiliary_data.get("success", False):
                return ToolResult(
                    llm_content=f"Error generating first scene: {first_scene_result.auxiliary_data.get('error', 'Unknown error')}",
                    user_display_content="Failed to generate first scene.",
                    is_error=True,
                )

            scene_video_paths.append(first_scene_path)

            for i, prompt in enumerate(prompts[1:], 1):
                # Extract last frame from previous scene
                prev_video_path = scene_video_paths[-1]
                last_frame_path = temp_dir / f"last_frame_{i - 1}.png"

                # Use ffmpeg to extract last frame
                extract_cmd = [
                    "ffmpeg",
                    "-i",
                    str(prev_video_path),
                    "-vf",
                    "select=eq(n\\,0)",
                    "-q:v",
                    "3",
                    "-vframes",
                    "1",
                    "-f",
                    "image2",
                    str(last_frame_path),
                    "-y",
                ]

                # Actually extract the very last frame
                extract_cmd = [
                    "ffmpeg",
                    "-sseof",
                    "-1",
                    "-i",
                    str(prev_video_path),
                    "-update",
                    "1",
                    "-q:v",
                    "1",
                    str(last_frame_path),
                    "-y",
                ]

                subprocess.run(extract_cmd, check=True, capture_output=True)

                # Generate next scene from last frame + prompt
                scene_filename = f"scene_{i}.mp4"
                scene_path = temp_dir / scene_filename

                scene_result = await image_tool.run_impl(
                    {
                        "image_file_path": str(
                            last_frame_path.relative_to(
                                self.workspace_manager.workspace_path(Path())
                            )
                        ),
                        "output_filename": str(
                            scene_path.relative_to(
                                self.workspace_manager.workspace_path(Path())
                            )
                        ),
                        "prompt": prompt,
                        "aspect_ratio": aspect_ratio,
                        "duration_seconds": str(duration_per_scene),
                        "allow_person_generation": True,
                    }
                )

                if not scene_result.auxiliary_data.get("success", False):
                    return ToolResult(
                        llm_content=f"Error generating scene {i}: {scene_result.auxiliary_data.get('error', 'Unknown error')}",
                        user_display_content=f"Failed to generate scene {i}.",
                        is_error=True,
                    )

                scene_video_paths.append(scene_path)

            # Combine all scenes into final video
            if len(scene_video_paths) == 1:
                # Only one scene, just copy it
                shutil.copy2(scene_video_paths[0], local_output_path)
            else:
                # Create file list for ffmpeg concat
                concat_file = temp_dir / "concat_list.txt"
                with open(concat_file, "w") as f:
                    for video_path in scene_video_paths:
                        f.write(f"file '{video_path.absolute()}'\n")

                # Concatenate videos
                concat_cmd = [
                    "ffmpeg",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_file),
                    "-c",
                    "copy",
                    str(local_output_path),
                    "-y",
                ]

                subprocess.run(concat_cmd, check=True, capture_output=True)

            return ToolResult(
                llm_content=f"Successfully generated long video with {len(prompts)} scenes and saved to '{relative_output_filename}'",
                user_display_content=f"Long video with {len(prompts)} scenes generated and saved to {relative_output_filename}",
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                llm_content=f"Error generating long video: {str(e)}",
                user_display_content="Failed to generate long video.",
                is_error=True,
            )
        finally:
            # Clean up temporary files
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e_cleanup:
                    print(
                        f"Warning: Failed to clean up temporary directory {temp_dir}: {e_cleanup}"
                    )

    async def execute_mcp_wrapper(self, 
        image_file_path: str, 
        output_filename: str, 
        prompts: list[str], 
        aspect_ratio: str = "16:9", 
        duration_seconds: int = 5, 
        enhance_prompt: bool = True
    ) -> str:        
        return await self._mcp_wrapper(
            tool_input={
                "image_file_path": image_file_path,
                "output_filename": output_filename,
                "prompts": prompts,
                "aspect_ratio": aspect_ratio,
                "duration_seconds": duration_seconds,
                "enhance_prompt": enhance_prompt,
            }
        )