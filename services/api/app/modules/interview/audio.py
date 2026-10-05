from __future__ import annotations

import io
import os
from typing import BinaryIO
import httpx


class AudioTranscriptionService:
    """Handles speech-to-text transcription using Whisper API or local whisper models with graceful fallback."""

    @classmethod
    def transcribe(cls, file_content: bytes, filename: str = "audio.wav") -> str:
        openai_key = os.getenv("OPENAI_API_KEY")
        
        # 1. Try OpenAI Whisper API if key is present
        if openai_key:
            try:
                headers = {"Authorization": f"Bearer {openai_key}"}
                files = {"file": (filename, file_content, "audio/wav")}
                data = {"model": "whisper-1"}
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data,
                    )
                    if resp.status_code == 200:
                        return resp.json().get("text", "").strip()
            except Exception:
                pass

        # 2. Try local whisper if installed
        try:
            import whisper  # type: ignore
            model = whisper.load_model("base")
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file.write(file_content)
                temp_path = temp_file.name
            try:
                result = model.transcribe(temp_path)
                return result.get("text", "").strip()
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except (ImportError, Exception):
            pass

        return ""
