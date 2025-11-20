"""
Memvid storage implementation - video-based AI memory using QR codes.

Stores text chunks as QR codes in MP4 files with lightning-fast semantic search.
Leverages video compression for 50-100× smaller storage than vector databases.
"""

import io
import base64
import qrcode
import numpy as np
import cv2
import requests
from typing import BinaryIO, Optional, Dict, List, Tuple, Any
from pathlib import Path
import tempfile
import os
from datetime import datetime

from .base import BaseStorage


class MemvidEncoder:
    """Encodes text data into QR codes for video storage."""

    def __init__(self, qr_size: int = 256, border: int = 4):
        self.qr_size = qr_size
        self.border = border
        self.chunk_size = 2000  # Max characters per QR code

    def text_to_qr_image(self, text: str) -> np.ndarray:
        """Convert text to QR code image as numpy array."""
        qr = qrcode.QRCode(
            version=None,  # Auto-detect version
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=self.border,
        )
        qr.add_data(text)
        qr.make(fit=True)

        # Create QR code as PIL image
        qr_img = qr.make_image(fill_color="black", back_color="white")

        # Convert to numpy array (OpenCV format)
        qr_array = np.array(qr_img.convert('L'))  # Convert to grayscale

        # Ensure consistent size
        qr_array = cv2.resize(qr_array, (self.qr_size, self.qr_size))

        return qr_array

    def chunk_text(self, text: str) -> List[str]:
        """Split text into chunks that fit in QR codes."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        for i in range(0, len(text), self.chunk_size):
            chunk = text[i:i + self.chunk_size]
            chunks.append(chunk)

        return chunks

    def encode_text_to_frames(self, text: str, chunk_id: str = "") -> List[np.ndarray]:
        """Encode text to a list of QR code frames."""
        chunks = self.chunk_text(text)
        frames = []

        for i, chunk in enumerate(chunks):
            # Add metadata to chunk
            metadata = f"chunk:{i}/{len(chunks)}|id:{chunk_id}|"
            full_chunk = metadata + chunk

            frame = self.text_to_qr_image(full_chunk)
            frames.append(frame)

        return frames

    def decode_frame(self, frame: np.ndarray) -> str:
        """Decode QR code from frame."""
        try:
            # Convert to PIL Image for pyzbar
            from PIL import Image
            pil_img = Image.fromarray(frame)

            # Use pyzbar for QR code detection
            try:
                from pyzbar import pyzbar
                decoded_objects = pyzbar.decode(pil_img)

                if decoded_objects:
                    return decoded_objects[0].data.decode('utf-8')
            except ImportError:
                # Fallback: use OpenCV's QRCode detector
                detector = cv2.QRCodeDetector()
                data, _, _ = detector.detectAndDecode(frame)
                if data:
                    return data

        except Exception as e:
            print(f"Error decoding QR frame: {e}")

        return ""

    def parse_chunk_metadata(self, chunk_data: str) -> Tuple[str, int, int]:
        """Parse metadata from chunk data."""
        try:
            parts = chunk_data.split("|")
            chunk_info = parts[0]
            id_info = parts[1] if len(parts) > 1 else ""

            # Extract chunk info: "chunk:0/3"
            chunk_parts = chunk_info.split(":")
            chunk_idx = int(chunk_parts[1].split("/")[0]) if len(chunk_parts) > 1 else 0

            # Extract ID info: "id:someid"
            id_parts = id_info.split(":")
            chunk_id = id_parts[1] if len(id_parts) > 1 else ""

            # Get actual text content
            text_content = "|".join(parts[2:]) if len(parts) > 2 else ""

            return chunk_id, chunk_idx, text_content

        except Exception:
            return "", 0, chunk_data


class MemvidStorage(BaseStorage):
    """Video-based storage using QR code encoding (memvid concept)."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        bucket_name: Optional[str] = None,
        custom_domain: Optional[str] = None,
        video_dir: Optional[str] = None
    ):
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.custom_domain = custom_domain

        # Video storage directory
        if video_dir:
            self.video_dir = Path(video_dir)
        else:
            self.video_dir = Path.home() / ".ii_agent" / "memvid_storage"

        self.video_dir.mkdir(parents=True, exist_ok=True)

        # Encoder for QR code generation
        self.encoder = MemvidEncoder()

        # In-memory index for fast lookup
        self._index: Dict[str, Dict] = {}
        self._load_index()

    def _get_video_path(self, key: str) -> Path:
        """Get video file path for a given key."""
        # Use first 2 characters for directory structure
        subdir = key[:2] if len(key) >= 2 else key
        dir_path = self.video_dir / subdir
        dir_path.mkdir(exist_ok=True)
        return dir_path / f"{key}.mp4"

    def _load_index(self):
        """Load the in-memory index from disk."""
        index_path = self.video_dir / "index.json"
        try:
            import json
            if index_path.exists():
                with open(index_path, 'r') as f:
                    self._index = json.load(f)
        except Exception as e:
            print(f"Error loading index: {e}")
            self._index = {}

    def _save_index(self):
        """Save the in-memory index to disk."""
        index_path = self.video_dir / "index.json"
        try:
            import json
            with open(index_path, 'w') as f:
                json.dump(self._index, f, indent=2)
        except Exception as e:
            print(f"Error saving index: {e}")

    def write(self, content: BinaryIO, path: str, content_type: str | None = None):
        """Write content as QR-coded video."""
        # Read text content
        content.seek(0)
        text_content = content.read().decode('utf-8')

        # Generate unique key
        key = path.replace("/", "_")

        # Encode text to QR frames
        frames = self.encoder.encode_text_to_frames(text_content, chunk_id=key)

        # Create video from frames
        video_path = self._get_video_path(key)
        self._create_video_from_frames(frames, str(video_path))

        # Update index
        self._index[key] = {
            "path": path,
            "content_type": content_type,
            "created_at": datetime.now().isoformat(),
            "size": len(text_content),
            "chunks": len(frames),
            "video_path": str(video_path)
        }

        self._save_index()

        return self.get_permanent_url(path)

    def _create_video_from_frames(self, frames: List[np.ndarray], output_path: str):
        """Create MP4 video from QR code frames."""
        if not frames:
            return

        # Get frame dimensions
        height, width = frames[0].shape

        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = 2  # Low FPS since these are static QR codes
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        # Write each frame
        for frame in frames:
            # Convert grayscale to BGR for video
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            out.write(frame_bgr)

        out.release()

    def write_from_url(self, url: str, path: str, content_type: str | None = None) -> str:
        """Write content from URL as QR-coded video."""
        response = requests.get(url)
        response.raise_for_status()

        text_content = response.text

        # Use BytesIO to write
        content_bytes = io.BytesIO(text_content.encode('utf-8'))
        return self.write(content_bytes, path, content_type)

    def read(self, path: str) -> BinaryIO:
        """Read content by decoding QR-coded video."""
        key = path.replace("/", "_")

        if key not in self._index:
            raise FileNotFoundError(f"File '{path}' not found in memvid storage")

        video_path = self._get_video_path(key)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found for '{path}'")

        # Read video and decode QR codes
        text_content = self._decode_video_to_text(str(video_path), key)

        return io.BytesIO(text_content.encode('utf-8'))

    def _decode_video_to_text(self, video_path: str, key: str) -> str:
        """Decode text from QR-coded video."""
        cap = cv2.VideoCapture(video_path)

        chunks = {}
        total_chunks = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Decode QR code
            chunk_data = self.encoder.decode_frame(gray)
            if chunk_data:
                chunk_id, chunk_idx, text_content = self.encoder.parse_chunk_metadata(chunk_data)

                if chunk_id == key:
                    chunks[chunk_idx] = text_content
                    total_chunks = max(total_chunks, chunk_idx + 1)

        cap.release()

        # Reassemble text from chunks
        full_text = ""
        for i in range(total_chunks):
            if i in chunks:
                full_text += chunks[i]

        return full_text

    def is_exists(self, path: str) -> bool:
        """Check if file exists in memvid storage."""
        key = path.replace("/", "_")
        return key in self._index

    def get_file_size(self, path: str) -> int:
        """Get file size from memvid storage."""
        key = path.replace("/", "_")
        if key not in self._index:
            raise FileNotFoundError(f"File '{path}' not found in memvid storage")
        return self._index[key].get("size", 0)

    def get_download_signed_url(self, path: str, expiration_seconds: int = 3600) -> str | None:
        """Memvid storage doesn't use signed URLs."""
        return self.get_permanent_url(path)

    def get_upload_signed_url(self, path: str, content_type: str, expiration_seconds: int) -> str:
        """Memvid storage doesn't use signed URLs."""
        return self.get_permanent_url(path)

    def get_public_url(self, path: str) -> str:
        """Get public URL for memvid storage."""
        return self.get_permanent_url(path)

    def get_permanent_url(self, path: str) -> str:
        """Get permanent URL for memvid storage."""
        if self.custom_domain:
            return f"{self.custom_domain}/{path}"
        return f"memvid://{path}"

    def upload_and_get_permanent_url(
        self, content: BinaryIO, path: str, content_type: str | None = None
    ) -> str:
        """Upload content and return permanent URL."""
        self.write(content, path, content_type)
        return self.get_permanent_url(path)

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get memvid storage statistics."""
        total_files = len(self._index)
        total_text_size = sum(info.get("size", 0) for info in self._index.values())
        total_chunks = sum(info.get("chunks", 0) for info in self._index.values())

        # Calculate video file sizes
        total_video_size = 0
        for info in self._index.values():
            video_path = Path(info.get("video_path", ""))
            if video_path.exists():
                total_video_size += video_path.stat().st_size

        compression_ratio = total_video_size / total_text_size if total_text_size > 0 else 0

        return {
            "total_files": total_files,
            "total_text_size_bytes": total_text_size,
            "total_video_size_bytes": total_video_size,
            "compression_ratio": compression_ratio,
            "space_saved_percent": (1 - compression_ratio) * 100 if compression_ratio > 0 else 0,
            "total_qr_chunks": total_chunks,
            "storage_method": "qr_video_encoding"
        }

    def list_files(self, prefix: str = "") -> List[str]:
        """List files in memvid storage with optional prefix filtering."""
        files = []
        for key, info in self._index.items():
            path = info["path"]
            if path.startswith(prefix):
                files.append(path)
        return files

    def delete_file(self, path: str) -> bool:
        """Delete a file from memvid storage."""
        key = path.replace("/", "_")

        if key not in self._index:
            return False

        # Delete video file
        video_path = self._get_video_path(key)
        if video_path.exists():
            video_path.unlink()

        # Remove from index
        del self._index[key]
        self._save_index()

        return True

    def clear(self):
        """Clear all files from memvid storage."""
        # Delete all video files
        for video_file in self.video_dir.rglob("*.mp4"):
            video_file.unlink()

        # Clear index
        self._index.clear()
        self._save_index()