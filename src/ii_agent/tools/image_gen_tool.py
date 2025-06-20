# src/ii_agent/tools/image_generate_tool.py

import os
from pathlib import Path
from typing import Any, Optional, Union, Literal
from io import BytesIO
from enum import Enum

try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

try:
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel
    HAS_VERTEX = True
except ImportError:
    HAS_VERTEX = False

from PIL import Image

from ii_agent.tools.base import MessageHistory, LLMTool, ToolImplOutput
from ii_agent.utils import WorkspaceManager
from ii_agent.core.storage.models.settings import Settings


class AspectRatio(str, Enum):
    SQUARE = "1:1"
    WIDE = "16:9"
    TALL = "9:16"
    LANDSCAPE = "4:3"
    PORTRAIT = "3:4"


class SafetyFilterLevel(str, Enum):
    BLOCK_SOME = "block_some"
    BLOCK_MOST = "block_most"
    BLOCK_FEW = "block_few"


class PersonGeneration(str, Enum):
    ALLOW_ADULT = "allow_adult"
    DONT_ALLOW = "dont_allow"
    ALLOW_ALL = "allow_all"


class APIType(str, Enum):
    GENAI = "genai"
    VERTEX = "vertex"


# Google AI Studio person generation mapping
GENAI_PERSON_GENERATION_MAP = {
    PersonGeneration.ALLOW_ADULT: "ALLOW_ADULT",
    PersonGeneration.DONT_ALLOW: "DONT_ALLOW",
    PersonGeneration.ALLOW_ALL: "ALLOW_ALL"
}

IMAGE_MODEL_NAME = "imagen-3.0-generate-002"
DEFAULT_OUTPUT_MIME_TYPE = "image/jpeg"
PNG_EXTENSION = ".png"


class ImageGenerationError(Exception):
    """Custom exception for image generation errors."""
    pass


class ImageGenerateTool(LLMTool):
    name = "generate_image_from_text"
    description = """Generates an image based on a text prompt using Google's Imagen 3 model via Vertex AI or Google AI Studio.
The generated image will be saved to the specified local path in the workspace as a PNG file."""
    
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "A detailed description of the image to be generated.",
            },
            "output_filename": {
                "type": "string",
                "description": "The desired relative path for the output PNG image file within the workspace (e.g., 'generated_images/my_image.png'). Must end with .png.",
            },
            "number_of_images": {
                "type": "integer",
                "default": 1,
                "description": "Number of images to generate (currently, the example shows 1, stick to 1 unless API supports more easily).",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": [ratio.value for ratio in AspectRatio],
                "default": AspectRatio.SQUARE.value,
                "description": "The aspect ratio for the generated image.",
            },
            "seed": {
                "type": "integer",
                "description": "(Optional) A seed for deterministic generation. If provided, add_watermark will be forced to False as they are mutually exclusive.",
            },
            "add_watermark": {
                "type": "boolean",
                "default": True,
                "description": "Whether to add a watermark to the generated image. Cannot be used with 'seed'.",
            },
            "safety_filter_level": {
                "type": "string",
                "enum": [level.value for level in SafetyFilterLevel],
                "default": SafetyFilterLevel.BLOCK_SOME.value,
                "description": "The safety filter level to apply.",
            },
            "person_generation": {
                "type": "string",
                "enum": [option.value for option in PersonGeneration],
                "default": PersonGeneration.ALLOW_ADULT.value,
                "description": "Controls the generation of people.",
            },
        },
        "required": ["prompt", "output_filename"],
    }

    def __init__(self, workspace_manager: WorkspaceManager, settings: Optional[Settings] = None):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.api_type: Optional[APIType] = None
        self.genai_client: Optional[Any] = None
        self.vertex_model: Optional[Any] = None
        
        self._initialize_api_client(settings)

    def _initialize_api_client(self, settings: Optional[Settings]) -> None:
        """Initialize the appropriate API client based on available settings."""
        if not settings or not settings.media_config:
            raise ImageGenerationError(
                "Settings with media_config must be provided for image generation"
            )
        
        media_config = settings.media_config
        
        # Try Google AI Studio first
        if hasattr(media_config, 'google_ai_studio_api_key') and media_config.google_ai_studio_api_key:
            self._initialize_genai_client(media_config.google_ai_studio_api_key)
        # Fall back to Vertex AI
        elif media_config.gcp_project_id and media_config.gcp_location:
            self._initialize_vertex_client(media_config.gcp_project_id, media_config.gcp_location)
        else:
            raise ImageGenerationError(
                "Either Google AI Studio API key or GCP project ID and location must be provided in settings.media_config"
            )

    def _initialize_genai_client(self, api_key: Any) -> None:
        """Initialize Google AI Studio client."""
        if not HAS_GENAI:
            raise ImageGenerationError("Google GenAI package not available")
        
        self.genai_client = genai.Client(api_key=api_key.get_secret_value())
        self.api_type = APIType.GENAI
        print("Using Google AI Studio for image generation")

    def _initialize_vertex_client(self, project_id: str, location: str) -> None:
        """Initialize Vertex AI client."""
        if not HAS_VERTEX:
            raise ImageGenerationError("Vertex AI package not available")
        
        vertexai.init(project=project_id, location=location)
        self.vertex_model = ImageGenerationModel.from_pretrained(IMAGE_MODEL_NAME)
        self.api_type = APIType.VERTEX
        print("Using Vertex AI for image generation")

    def _validate_input(self, tool_input: dict[str, Any]) -> None:
        """Validate the tool input parameters."""
        output_filename = tool_input["output_filename"]
        
        if not output_filename.lower().endswith(PNG_EXTENSION):
            raise ImageGenerationError(
                f"Output filename must end with {PNG_EXTENSION} for Imagen generation"
            )
        
        # Validate seed and watermark mutual exclusivity
        if tool_input.get("seed") is not None and tool_input.get("add_watermark", True):
            tool_input["add_watermark"] = False

    def _prepare_output_path(self, relative_filename: str) -> Path:
        """Prepare the output path and create directories if needed."""
        local_output_path = self.workspace_manager.workspace_path(Path(relative_filename))
        local_output_path.parent.mkdir(parents=True, exist_ok=True)
        return local_output_path

    def _generate_with_genai(self, prompt: str, tool_input: dict[str, Any]) -> Image.Image:
        """Generate image using Google AI Studio API."""
        if not self.genai_client:
            raise ImageGenerationError("GenAI client not initialized")
        
        config = {
            "number_of_images": tool_input.get("number_of_images", 1),
            "output_mime_type": DEFAULT_OUTPUT_MIME_TYPE,
            "aspect_ratio": tool_input.get("aspect_ratio", AspectRatio.SQUARE.value),
            "person_generation": GENAI_PERSON_GENERATION_MAP.get(
                PersonGeneration(tool_input.get("person_generation", PersonGeneration.ALLOW_ADULT.value)),
                "ALLOW_ADULT"
            ),
        }
        
        result = self.genai_client.models.generate_images(
            model=f"models/{IMAGE_MODEL_NAME}",
            prompt=prompt,
            config=config,
        )
        
        if not result.generated_images:
            raise ImageGenerationError("No images returned from Google AI Studio API")
        
        generated_image = result.generated_images[0]
        return Image.open(BytesIO(generated_image.image.image_bytes))

    def _generate_with_vertex(self, prompt: str, tool_input: dict[str, Any]) -> Any:
        """Generate image using Vertex AI API."""
        if not self.vertex_model:
            raise ImageGenerationError("Vertex AI model not initialized")
        
        generate_params = {
            "number_of_images": tool_input.get("number_of_images", 1),
            "language": "en",
            "aspect_ratio": tool_input.get("aspect_ratio", AspectRatio.SQUARE.value),
            "safety_filter_level": tool_input.get("safety_filter_level", SafetyFilterLevel.BLOCK_SOME.value),
            "person_generation": tool_input.get("person_generation", PersonGeneration.ALLOW_ADULT.value),
        }
        
        images = self.vertex_model.generate_images(prompt=prompt, **generate_params)
        
        if not images:
            raise ImageGenerationError("No images returned from Vertex AI API")
        
        return images[0]

    def _save_image(self, image: Union[Image.Image, Any], output_path: Path, is_pil_image: bool = True) -> None:
        """Save the generated image to the specified path."""
        if is_pil_image:
            image.save(str(output_path), "PNG")
        else:
            # Vertex AI image object
            image.save(location=str(output_path), include_generation_parameters=False)

    def _get_output_url(self, relative_filename: str) -> str:
        """Generate the output URL for the saved image."""
        if hasattr(self.workspace_manager, "file_server_port"):
            return f"http://localhost:{self.workspace_manager.file_server_port}/workspace/{relative_filename}"
        return f"(Local path: {relative_filename})"

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        """Generate an image based on the provided text prompt."""
        try:
            # Validate input
            self._validate_input(tool_input)
            
            prompt = tool_input["prompt"]
            relative_output_filename = tool_input["output_filename"]
            
            # Prepare output path
            local_output_path = self._prepare_output_path(relative_output_filename)
            
            # Generate image based on API type
            if self.api_type == APIType.GENAI:
                image = self._generate_with_genai(prompt, tool_input)
                self._save_image(image, local_output_path, is_pil_image=True)
            elif self.api_type == APIType.VERTEX:
                image = self._generate_with_vertex(prompt, tool_input)
                self._save_image(image, local_output_path, is_pil_image=False)
            else:
                raise ImageGenerationError("No image generation API is configured")
            
            # Generate output URL
            output_url = self._get_output_url(relative_output_filename)
            
            return ToolImplOutput(
                f"Successfully generated image from text and saved to '{relative_output_filename}'. View at: {output_url}",
                f"Image generated and saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
                    "url": output_url,
                },
            )
            
        except ImageGenerationError as e:
            return ToolImplOutput(
                f"Image generation failed: {str(e)}",
                "Failed to generate image from text.",
                {"success": False, "error": str(e)},
            )
        except Exception as e:
            return ToolImplOutput(
                f"Unexpected error during image generation: {str(e)}",
                "Failed to generate image from text.",
                {"success": False, "error": str(e)},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        """Return a message indicating the tool has started."""
        return f"Generating image from text prompt, saving to: {tool_input['output_filename']}"