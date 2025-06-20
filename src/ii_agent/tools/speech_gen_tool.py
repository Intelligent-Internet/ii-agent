# src/ii_agent/tools/speech_gen_tool.py

import os
from pathlib import Path
from typing import Any, Optional, List, Dict
import base64
import struct
import mimetypes

from google import genai
from google.genai import types

from ii_agent.tools.base import (
    MessageHistory,
    LLMTool,
    ToolImplOutput,
)
from ii_agent.utils import WorkspaceManager
from ii_agent.core.storage.models.settings import Settings

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Available voices from the API documentation
AVAILABLE_VOICES = [
    "achernar", "achird", "algenib", "algieba", "alnilam", "aoede", "autonoe", 
    "callirrhoe", "charon", "despina", "enceladus", "erinome", "fenrir", 
    "gacrux", "iapetus", "kore", "laomedeia", "leda", "orus", "puck", 
    "pulcherrima", "rasalgethi", "sadachbia", "sadaltager", "schedar", 
    "sulafat", "umbriel", "vindemiatrix", "zephyr", "zubenelgenubi"
]

# Voice characteristics for user reference
VOICE_CHARACTERISTICS = {
    "achernar": "Clear, professional voice",
    "achird": "Deep, mysterious voice",
    "algenib": "Warm, friendly voice",
    "algieba": "Bright, energetic voice",
    "alnilam": "Smooth, sophisticated voice",
    "aoede": "Musical, melodic voice",
    "autonoe": "Gentle, soothing voice",
    "callirrhoe": "Elegant, refined voice",
    "charon": "Deep, authoritative voice",
    "despina": "Light, cheerful voice",
    "enceladus": "Cool, measured voice",
    "erinome": "Warm, nurturing voice",
    "fenrir": "Strong, powerful voice",
    "gacrux": "Rich, resonant voice",
    "iapetus": "Wise, thoughtful voice",
    "kore": "Cheerful, upbeat voice",
    "laomedeia": "Graceful, flowing voice",
    "leda": "Soft, delicate voice",
    "orus": "Bold, confident voice",
    "puck": "Playful, energetic voice",
    "pulcherrima": "Beautiful, melodious voice",
    "rasalgethi": "Dramatic, expressive voice",
    "sadachbia": "Calm, reassuring voice",
    "sadaltager": "Friendly, approachable voice",
    "schedar": "Royal, commanding voice",
    "sulafat": "Smooth, professional voice",
    "umbriel": "Dark, mysterious voice",
    "vindemiatrix": "Bright, enthusiastic voice",
    "zephyr": "Bright, warm voice suitable for narration",
    "zubenelgenubi": "Balanced, neutral voice"
}

# Available models for speech generation
SPEECH_MODELS = ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]

def save_binary_file(file_name, data):
    f = open(file_name, "wb")
    f.write(data)
    f.close()
    print(f"File saved to to: {file_name}")


def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """Generates a WAV file header for the given audio data and parameters."""
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", chunk_size, b"WAVE", b"fmt ", 16, 1,
        num_channels, sample_rate, byte_rate, block_align,
        bits_per_sample, b"data", data_size
    )
    return header + audio_data


def parse_audio_mime_type(mime_type: str) -> dict[str, int]:
    """Parses bits per sample and rate from an audio MIME type string."""
    bits_per_sample = 16
    rate = 24000

    parts = mime_type.split(";")
    for param in parts:
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate_str = param.split("=", 1)[1]
                rate = int(rate_str)
            except (ValueError, IndexError):
                pass
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except (ValueError, IndexError):
                pass

    return {"bits_per_sample": bits_per_sample, "rate": rate}


class SingleSpeakerSpeechGenerationTool(LLMTool):
    name = "generate_speech_single_speaker"
    description = f"""Generates speech audio from text using Google's Gemini TTS with a single speaker.
The generated audio will be saved as an MP3 file in the workspace.

Available voices: {', '.join(AVAILABLE_VOICES[:10])} and {len(AVAILABLE_VOICES)-10} more.
Supports tone and style control through natural language instructions (e.g., "Say cheerfully:", "Read with excitement:").
Automatic language detection from input text."""
    
    input_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to convert to speech. Can include tone/style instructions like 'Say cheerfully: Hello world!'"
            },
            "output_filename": {
                "type": "string",
                "description": "The desired relative path for the output MP3 audio file within the workspace (e.g., 'audio/speech.mp3'). Must end with .mp3."
            },
            "voice": {
                "type": "string",
                "enum": AVAILABLE_VOICES,
                "default": "kore",
                "description": f"The voice to use for speech generation. Available voices: {', '.join(AVAILABLE_VOICES)}"
            },
            "model": {
                "type": "string",
                "enum": SPEECH_MODELS,
                "default": "gemini-2.5-flash-preview-tts",
                "description": "The model to use for speech generation. Flash is faster, Pro has better quality."
            }
        },
        "required": ["text", "output_filename"]
    }

    def __init__(self, workspace_manager: WorkspaceManager, settings: Settings):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.settings = settings
        
        if settings and settings.media_config:
            self.google_ai_studio_api_key = settings.media_config.google_ai_studio_api_key
        else:
            raise ValueError(
                "Required GEMINI_API_KEY for speech generation."
            )
        
        if self.google_ai_studio_api_key:
            self.client = genai.Client(
                http_options={"api_version": "v1beta"},
                api_key=self.google_ai_studio_api_key.get_secret_value(),
            )
            print("Initialized Google AI Studio for speech generation")
        else:
            raise ValueError(
                "Required GEMINI_API_KEY for speech generation."
            )

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        text = tool_input["text"]
        relative_output_filename = tool_input["output_filename"]
        voice = tool_input.get("voice", "kore")
        model = tool_input.get("model", "gemini-2.5-flash-preview-tts")
        
        if not relative_output_filename.lower().endswith(".mp3"):
            return ToolImplOutput(
                "Error: output_filename must end with .mp3",
                "Invalid output filename for audio.",
                {"success": False, "error": "Output filename must be .mp3"},
            )
        
        local_output_path = self.workspace_manager.workspace_path(
            Path(relative_output_filename)
        )
        local_output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Generate speech without streaming
            response = self.client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["audio"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice
                            )
                        )
                    ),
                )
            )
            
            # Extract audio data from response
            if not response.candidates or not response.candidates[0].content.parts:
                return ToolImplOutput(
                    "Error: No audio generated from the text.",
                    "Speech generation failed.",
                    {"success": False, "error": "No audio output from API"},
                )
            
        
            # Find the audio part
            audio_part = None
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data.mime_type.startswith('audio'):
                    audio_part = part
                    break
            
            if not audio_part:
                return ToolImplOutput(
                    "Error: No audio data found in the response.",
                    "Speech generation failed.",
                    {"success": False, "error": "No audio data in response"},
                )
            
            data = convert_to_wav(response.candidates[0].content.parts[0].inline_data.data, response.candidates[0].content.parts[0].inline_data.mime_type)    
            
            save_binary_file(relative_output_filename, data)
             
            output_url = (
                f"http://localhost:{self.workspace_manager.file_server_port}/workspace/{relative_output_filename}"
                if hasattr(self.workspace_manager, "file_server_port")
                else f"(Local path: {relative_output_filename})"
            )
            
            return ToolImplOutput(
                f"Successfully generated speech and saved to '{relative_output_filename}'. Voice: {voice}. Listen at: {output_url}",
                f"Speech generated and saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
                    "url": output_url,
                    "voice": voice,
                    "model": model
                },
            )
            
        except Exception as e:
            return ToolImplOutput(
                f"Error generating speech: {str(e)}",
                "Failed to generate speech.",
                {"success": False, "error": str(e)},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Generating speech with voice '{tool_input.get('voice', 'Kore')}' for file: {tool_input['output_filename']}"