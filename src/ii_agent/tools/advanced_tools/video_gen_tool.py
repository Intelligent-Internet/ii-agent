# src/ii_agent/tools/video_generate_from_text_tool.py
import os
import time
import uuid
import shutil
import subprocess
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

MEDIA_GCP_PROJECT_ID = os.environ.get("MEDIA_GCP_PROJECT_ID")
MEDIA_GCP_LOCATION = os.environ.get("MEDIA_GCP_LOCATION")
MEDIA_GCS_OUTPUT_BUCKET = os.environ.get("MEDIA_GCS_OUTPUT_BUCKET")
DEFAULT_MODEL = "veo-2.0-generate-001"


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
        if not MEDIA_GCS_OUTPUT_BUCKET or not MEDIA_GCS_OUTPUT_BUCKET.startswith("gs://"):
            raise ValueError(
                "MEDIA_GCS_OUTPUT_BUCKET environment variable must be set to a valid GCS URI (e.g., gs://my-bucket-name)"
            )
        self.workspace_manager = workspace_manager
        if not MEDIA_GCP_PROJECT_ID or not MEDIA_GCP_LOCATION:
            raise ValueError("MEDIA_GCP_PROJECT_ID and MEDIA_GCP_LOCATION environment variables not set.")
        self.client = genai.Client(
            project=MEDIA_GCP_PROJECT_ID, location=MEDIA_GCP_LOCATION, vertexai=True
        )
        self.video_model = DEFAULT_MODEL

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
        gcs_output_uri = f"{MEDIA_GCS_OUTPUT_BUCKET.rstrip('/')}/{unique_gcs_filename}"

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

            return ToolImplOutput(
                f"Successfully generated video from text and saved to '{relative_output_filename}'",
                f"Video generated and saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
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
        if not MEDIA_GCP_PROJECT_ID or not MEDIA_GCP_LOCATION:
            raise ValueError("MEDIA_GCP_PROJECT_ID and MEDIA_GCP_LOCATION environment variables not set.")
        self.genai_client = genai.Client(
            project=MEDIA_GCP_PROJECT_ID, location=MEDIA_GCP_LOCATION, vertexai=True
        )
        self.video_model = DEFAULT_MODEL

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
            f"{MEDIA_GCS_OUTPUT_BUCKET.rstrip('/')}/{temp_gcs_image_filename}"
        )

        generated_video_gcs_uri_for_cleanup = None  # For finally block

        try:
            upload_to_gcs(local_input_image_path, temp_gcs_image_uri)

            unique_gcs_video_filename = f"veo_temp_output_{uuid.uuid4().hex}.mp4"
            gcs_output_video_uri = (
                f"{MEDIA_GCS_OUTPUT_BUCKET.rstrip('/')}/{unique_gcs_video_filename}"
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

            return ToolImplOutput(
                f"Successfully generated video from image '{relative_image_path}' and saved to '{relative_output_filename}'.",
                f"Video from image generated and saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
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

class LongVideoGenerateFromTextTool(LLMTool):
    name = "generate_long_video_from_text"
    description = f"""Generates a long video (>= 10 seconds) based on a sequence of text prompts. Each prompt presents a new scene in the video, each scene is minimum 5 and maximum 8 seconds (preferably 5 seconds). Video is combined sequentially from the first scene to the last.
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

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.workspace_manager = workspace_manager
        if not MEDIA_GCP_PROJECT_ID:
            raise ValueError("MEDIA_GCP_PROJECT_ID environment variable not set.")

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        prompts = tool_input["prompts"]
        relative_output_filename = tool_input["output_filename"]
        aspect_ratio = tool_input.get("aspect_ratio", "16:9")
        duration_seconds = int(tool_input["duration_seconds"])
        enhance_prompt = tool_input.get("enhance_prompt", True)

        if not relative_output_filename.lower().endswith(".mp4"):
            return ToolImplOutput(
                "Error: output_filename must end with .mp4",
                "Invalid output filename for video.",
                {"success": False, "error": "Output filename must be .mp4"},
            )
        
        if len(prompts) == 0:
            return ToolImplOutput(
                "Error: At least one prompt is required",
                "No prompts provided for video generation.",
                {"success": False, "error": "No prompts provided"},
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
            first_scene_filename = f"scene_0.mp4"
            first_scene_path = temp_dir / first_scene_filename
            
            text_tool = VideoGenerateFromTextTool(self.workspace_manager)
            first_scene_result = text_tool.run_impl({
                "prompt": prompts[0],
                "output_filename": str(first_scene_path.relative_to(self.workspace_manager.workspace_path(Path()))),
                "aspect_ratio": aspect_ratio,
                "duration_seconds": str(duration_per_scene),
                "enhance_prompt": enhance_prompt,
                "allow_person_generation": True,
            })
            
            if not first_scene_result.auxiliary_data.get("success", False):
                return ToolImplOutput(
                    f"Error generating first scene: {first_scene_result.auxiliary_data.get('error', 'Unknown error')}",
                    "Failed to generate first scene.",
                    {"success": False, "error": "First scene generation failed"},
                )
            
            scene_video_paths.append(first_scene_path)
            
            # Generate subsequent scenes from last frame + prompt
            image_tool = VideoGenerateFromImageTool(self.workspace_manager)
            
            for i, prompt in enumerate(prompts[1:], 1):
                # Extract last frame from previous scene
                prev_video_path = scene_video_paths[-1]
                last_frame_path = temp_dir / f"last_frame_{i-1}.png"
                
                # Use ffmpeg to extract last frame
                extract_cmd = [
                    "ffmpeg", "-i", str(prev_video_path), 
                    "-vf", "select=eq(n\\,0)", "-q:v", "3", 
                    "-vframes", "1", "-f", "image2", 
                    str(last_frame_path), "-y"
                ]
                
                # Actually extract the very last frame
                extract_cmd = [
                    "ffmpeg", "-sseof", "-1", "-i", str(prev_video_path),
                    "-update", "1", "-q:v", "1", str(last_frame_path), "-y"
                ]
                
                subprocess.run(extract_cmd, check=True, capture_output=True)
                
                # Generate next scene from last frame + prompt
                scene_filename = f"scene_{i}.mp4"
                scene_path = temp_dir / scene_filename
                
                scene_result = image_tool.run_impl({
                    "image_file_path": str(last_frame_path.relative_to(self.workspace_manager.workspace_path(Path()))),
                    "output_filename": str(scene_path.relative_to(self.workspace_manager.workspace_path(Path()))),
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "duration_seconds": str(duration_per_scene),
                    "allow_person_generation": True,
                })
                
                if not scene_result.auxiliary_data.get("success", False):
                    return ToolImplOutput(
                        f"Error generating scene {i}: {scene_result.auxiliary_data.get('error', 'Unknown error')}",
                        f"Failed to generate scene {i}.",
                        {"success": False, "error": f"Scene {i} generation failed"},
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
                    "ffmpeg", "-f", "concat", "-safe", "0", 
                    "-i", str(concat_file), "-c", "copy", 
                    str(local_output_path), "-y"
                ]
                
                subprocess.run(concat_cmd, check=True, capture_output=True)
            

            return ToolImplOutput(
                f"Successfully generated long video with {len(prompts)} scenes and saved to '{relative_output_filename}'",
                f"Long video with {len(prompts)} scenes generated and saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
                    "num_scenes": len(prompts),
                },
            )

        except Exception as e:
            return ToolImplOutput(
                f"Error generating long video: {str(e)}",
                "Failed to generate long video.",
                {"success": False, "error": str(e)},
            )
        finally:
            # Clean up temporary files
            
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e_cleanup:
                    print(f"Warning: Failed to clean up temporary directory {temp_dir}: {e_cleanup}")

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        num_scenes = len(tool_input.get("prompts", []))
        return f"Generating long video with {num_scenes} scenes for file: {tool_input['output_filename']}"


class LongVideoGenerateFromImageTool(LLMTool):
    name = "generate_long_video_from_image"
    description = f"""Generates a long video (>= 10 seconds) based on input image and a sequence of text prompts. Each prompt presents a new scene in the video, each scene is minimum 5 and maximum 8 seconds (preferably 5 seconds). Video is combined sequentially from the first scene to the last.
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
        "required": ["image_file_path", "prompts", "output_filename", "duration_seconds"],
    }

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.workspace_manager = workspace_manager

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        image_file_path = tool_input["image_file_path"]
        prompts = tool_input["prompts"]
        relative_output_filename = tool_input["output_filename"]
        aspect_ratio = tool_input.get("aspect_ratio", "16:9")
        duration_seconds = int(tool_input["duration_seconds"])
        enhance_prompt = tool_input.get("enhance_prompt", True)

        if not relative_output_filename.lower().endswith(".mp4"):
            return ToolImplOutput(
                "Error: output_filename must end with .mp4",
                "Invalid output filename for video.",
                {"success": False, "error": "Output filename must be .mp4"},
            )
        
        if len(prompts) == 0:
            return ToolImplOutput(
                "Error: At least one prompt is required",
                "No prompts provided for video generation.",
                {"success": False, "error": "No prompts provided"},
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
            first_scene_filename = f"scene_0.mp4"
            first_scene_path = temp_dir / first_scene_filename
            
            image_tool = VideoGenerateFromImageTool(self.workspace_manager)
            first_scene_result = image_tool.run_impl({
                "image_file_path": image_file_path,
                "prompt": prompts[0],
                "output_filename": str(first_scene_path.relative_to(self.workspace_manager.workspace_path(Path()))),
                "aspect_ratio": aspect_ratio,
                "duration_seconds": str(duration_per_scene),
                "enhance_prompt": enhance_prompt,
                "allow_person_generation": True,
            })
            
            if not first_scene_result.auxiliary_data.get("success", False):
                return ToolImplOutput(
                    f"Error generating first scene: {first_scene_result.auxiliary_data.get('error', 'Unknown error')}",
                    "Failed to generate first scene.",
                    {"success": False, "error": "First scene generation failed"},
                )
            
            scene_video_paths.append(first_scene_path)
            
            for i, prompt in enumerate(prompts[1:], 1):
                # Extract last frame from previous scene
                prev_video_path = scene_video_paths[-1]
                last_frame_path = temp_dir / f"last_frame_{i-1}.png"
                
                # Use ffmpeg to extract last frame
                extract_cmd = [
                    "ffmpeg", "-i", str(prev_video_path), 
                    "-vf", "select=eq(n\\,0)", "-q:v", "3", 
                    "-vframes", "1", "-f", "image2", 
                    str(last_frame_path), "-y"
                ]
                
                # Actually extract the very last frame
                extract_cmd = [
                    "ffmpeg", "-sseof", "-1", "-i", str(prev_video_path),
                    "-update", "1", "-q:v", "1", str(last_frame_path), "-y"
                ]
                
                subprocess.run(extract_cmd, check=True, capture_output=True)
                
                # Generate next scene from last frame + prompt
                scene_filename = f"scene_{i}.mp4"
                scene_path = temp_dir / scene_filename
                
                scene_result = image_tool.run_impl({
                    "image_file_path": str(last_frame_path.relative_to(self.workspace_manager.workspace_path(Path()))),
                    "output_filename": str(scene_path.relative_to(self.workspace_manager.workspace_path(Path()))),
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "duration_seconds": str(duration_per_scene),
                    "allow_person_generation": True,
                })
                
                if not scene_result.auxiliary_data.get("success", False):
                    return ToolImplOutput(
                        f"Error generating scene {i}: {scene_result.auxiliary_data.get('error', 'Unknown error')}",
                        f"Failed to generate scene {i}.",
                        {"success": False, "error": f"Scene {i} generation failed"},
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
                    "ffmpeg", "-f", "concat", "-safe", "0", 
                    "-i", str(concat_file), "-c", "copy", 
                    str(local_output_path), "-y"
                ]
                
                subprocess.run(concat_cmd, check=True, capture_output=True)
            
            return ToolImplOutput(
                f"Successfully generated long video with {len(prompts)} scenes and saved to '{relative_output_filename}'",
                f"Long video with {len(prompts)} scenes generated and saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
                    "num_scenes": len(prompts),
                },
            )

        except Exception as e:
            return ToolImplOutput(
                f"Error generating long video: {str(e)}",
                "Failed to generate long video.",
                {"success": False, "error": str(e)},
            )
        finally:
            # Clean up temporary files
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e_cleanup:
                    print(f"Warning: Failed to clean up temporary directory {temp_dir}: {e_cleanup}")

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        num_scenes = len(tool_input.get("prompts", []))
        return f"Generating long video with {num_scenes} scenes for file: {tool_input['output_filename']}"
