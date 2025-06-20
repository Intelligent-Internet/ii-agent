import base64
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Optional
from openai import APIError, AzureOpenAI

from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)

from ii_agent.utils import WorkspaceManager
from ii_agent.llm.message_history import MessageHistory

SUPPORTED_AUDIO_FORMATS = [
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".oga",
    ".ogg",
    ".wav",
    ".webm",
]


class AudioTranscribeTool(LLMTool):
    name = "audio_transcribe"
    description = f"""Transcribes audio content from a file located in the workspace using OpenAI Whisper.
Supported file formats: {", ".join(SUPPORTED_AUDIO_FORMATS)}"""
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The relative path to the audio file within the workspace (e.g., 'uploads/meeting_notes.mp3').",
            }
        },
        "required": ["file_path"],
    }

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.client = AzureOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            azure_endpoint=os.getenv("OPENAI_AZURE_ENDPOINT"),
            azure_deployment="gpt-4o-transcribe",
            api_version="2025-01-01-preview",
        )

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        relative_file_path = tool_input["file_path"]
        full_file_path = self.workspace_manager.workspace_path(Path(relative_file_path))

        if not full_file_path.exists():
            return ToolImplOutput(
                f"Error: File not found at {relative_file_path}",
                f"File not found at {relative_file_path}",
                {"success": False, "error": "File not found"},
            )
        if not full_file_path.is_file():
            return ToolImplOutput(
                f"Error: Path {relative_file_path} is not a file.",
                f"Path {relative_file_path} is not a file.",
                {"success": False, "error": "Path is not a file"},
            )
        if full_file_path.suffix.lower() not in SUPPORTED_AUDIO_FORMATS:
            return ToolImplOutput(
                f"Error: File format {full_file_path.suffix} is not supported for transcription.",
                f"Unsupported audio format: {full_file_path.suffix}",
                {"success": False, "error": "Unsupported audio format"},
            )

        try:
            with open(full_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="gpt-4o-transcribe", file=audio_file
                )

            transcribed_text = transcript.text if transcript else ""

            return ToolImplOutput(
                transcribed_text,
                f"Successfully transcribed audio from {relative_file_path}",
                {"success": True, "transcribed_chars": len(transcribed_text)},
            )
        except APIError as e:
            return ToolImplOutput(
                f"Error transcribing audio file {relative_file_path}: OpenAI API Error - {str(e)}",
                f"Failed to transcribe {relative_file_path} due to API error.",
                {"success": False, "error": f"OpenAI API Error: {str(e)}"},
            )
        except Exception as e:
            return ToolImplOutput(
                f"Error transcribing audio file {relative_file_path}: {str(e)}",
                f"Failed to transcribe {relative_file_path}",
                {"success": False, "error": str(e)},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Transcribing audio file: {tool_input['file_path']}"


AVAILABLE_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


class AudioGenerateTool(LLMTool):
    name = "generate_audio_response"
    description = f"""Generates speech audio from the provided text using OpenAI's TTS model (gpt-4o-audio-preview).
Saves the output as an MP3 file in the workspace. Available voices: {", ".join(AVAILABLE_VOICES)}."""
    input_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text content to convert to speech.",
            },
            "output_filename": {
                "type": "string",
                "description": "The desired relative path for the output MP3 file within the workspace (e.g., 'generated_audio/response.mp3'). Should end with '.mp3'.",
            },
            "voice": {
                "type": "string",
                "enum": AVAILABLE_VOICES,
                "default": "alloy",
                "description": "The voice to use for the speech synthesis.",
            },
            "temperature": {
                "type": "number",
                "default": 0.8,
                "description": "Controls randomness: lowering results in less random completions. Values closer to 0 make output more deterministic.",
            },
            "system_prompt": {
                "type": "string",
                "description": "(Optional) A system prompt to guide the voice actor persona (e.g., 'You are a cheerful assistant.')",
                "default": "You are a helpful voice assistant.",
            },
        },
        "required": ["text", "output_filename"],
    }

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.client = AzureOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            azure_endpoint=os.getenv("OPENAI_AZURE_ENDPOINT"),
            azure_deployment="gpt-4o-audio-preview",
            api_version="2025-01-01-preview",
        )
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("\n--- WARNING ---")
            print("`ffmpeg` command not found or failed to execute.")
            print("The AudioGenerateTool requires ffmpeg to convert WAV to MP3.")
            print("Please install ffmpeg on your system and ensure it's in your PATH.")
            print(
                "You can typically install it via your system's package manager (e.g., `apt install ffmpeg`, `brew install ffmpeg`)."
            )
            print("Audio generation might fail without ffmpeg.")
            print("---------------\n")

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        print("Initializing AudioGenerateTool $$$$$")
        text_to_speak = tool_input["text"]
        relative_output_filename = tool_input["output_filename"]
        voice = tool_input.get("voice", "alloy")
        temperature = tool_input.get("temperature", 0.8)
        system_prompt = tool_input.get(
            "system_prompt", "You are a helpful voice assistant."
        )

        if not relative_output_filename.lower().endswith(".mp3"):
            return ToolImplOutput(
                "Error: output_filename must end with .mp3",
                "Invalid output filename",
                {"success": False, "error": "Output filename must be .mp3"},
            )

        output_mp3_path = self.workspace_manager.workspace_path(
            Path(relative_output_filename)
        )
        # Ensure parent directory exists
        output_mp3_path.parent.mkdir(parents=True, exist_ok=True)

        # Use a temporary, unique WAV filename based on hash like in the tutorial
        m = hashlib.sha256()
        m.update(f"{system_prompt}_{text_to_speak}_{temperature}_{voice}".encode())
        temp_wav_filename = f"{m.hexdigest()[:16]}.wav"
        temp_wav_path = self.workspace_manager.workspace_path(
            Path("uploads") / temp_wav_filename
        )  # Store temp in uploads
        temp_wav_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure uploads exists

        try:
            completion = self.client.chat.completions.create(
                model="gpt-4o-audio-preview",
                modalities=["text", "audio"],
                audio={"voice": voice, "format": "wav"},  # API gives WAV
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": text_to_speak.strip()},
                ],
                temperature=temperature,
            )

            if not completion.choices or not completion.choices[0].message.audio:
                raise ValueError("No audio data received from API.")

            wav_bytes = base64.b64decode(completion.choices[0].message.audio.data)

            # 1. Save the temporary WAV file
            with open(temp_wav_path, "wb") as f:
                f.write(wav_bytes)

            # 2. Convert WAV to MP3 using ffmpeg
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",  # Overwrite output files without asking
                        "-i",
                        str(temp_wav_path),
                        "-acodec",
                        "libmp3lame",
                        "-b:a",
                        "64k",  # Bitrate for compression
                        str(output_mp3_path),
                    ],
                    check=True,  # Raise error if ffmpeg fails
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
            except FileNotFoundError:
                # ffmpeg not found warning already printed in __init__
                # Attempt to return WAV path instead if conversion fails?
                # For now, let's return an error indicating conversion failure.
                os.remove(temp_wav_path)  # Clean up temp file
                return ToolImplOutput(
                    "Error: ffmpeg command not found. Could not convert audio to MP3.",
                    "ffmpeg not found, conversion failed.",
                    {"success": False, "error": "ffmpeg not found"},
                )
            except subprocess.CalledProcessError as ffmpeg_err:
                os.remove(temp_wav_path)  # Clean up temp file
                return ToolImplOutput(
                    f"Error converting audio to MP3 using ffmpeg: {ffmpeg_err}",
                    "ffmpeg conversion failed.",
                    {"success": False, "error": f"ffmpeg error: {ffmpeg_err}"},
                )

            # 3. Delete temporary WAV file
            try:
                os.remove(temp_wav_path)
            except OSError as e:
                print(
                    f"Warning: Could not delete temporary WAV file {temp_wav_path}: {e}"
                )  # Non-fatal warning

            output_url = (
                f"http://localhost:{self.workspace_manager.file_server_port}/workspace/{relative_output_filename}"
                if hasattr(self.workspace_manager, "file_server_port")
                else f"(Local path: {relative_output_filename})"
            )

            return ToolImplOutput(
                f"Successfully generated audio and saved as MP3 to {relative_output_filename}. Playback URL (if server running): {output_url}",
                f"Generated audio saved to {relative_output_filename}",
                {
                    "success": True,
                    "output_path": relative_output_filename,
                    "url": output_url,
                },
            )

        except APIError as e:
            if temp_wav_path.exists():
                os.remove(temp_wav_path)  # Clean up temp file
            return ToolImplOutput(
                f"Error generating audio: OpenAI API Error - {str(e)}",
                "Failed to generate audio due to API error.",
                {"success": False, "error": f"OpenAI API Error: {str(e)}"},
            )
        except Exception as e:
            if temp_wav_path.exists():
                os.remove(temp_wav_path)  # Clean up temp file
            return ToolImplOutput(
                f"Error generating audio: {str(e)}",
                "Failed to generate audio",
                {"success": False, "error": str(e)},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Generating audio for file: {tool_input['output_filename']}"
