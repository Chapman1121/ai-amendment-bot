import base64
import json
from connection import ask_ai_audio


def audio_file_to_base64(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def transcribe_audio_with_gemini(audio_path: str):
    audio_base64 = audio_file_to_base64(audio_path)

    prompt = """
Transcribe this audio as accurately as possible.

Requirements:
- Handle accented English carefully.
- Preserve spoken wording as accurately as possible.
- Add natural punctuation.
- Return ONLY valid JSON.
- Do not add explanation text before or after JSON.

Return in this format:
{
  "transcript": "full transcript here",
  "segments": [
    {
      "start": "00:00",
      "end": "00:05",
      "text": "segment text here"
    }
  ]
}
"""

    result = ask_ai_audio(prompt, audio_base64).strip()

    start = result.find("{")
    end = result.rfind("}") + 1

    if start == -1 or end == 0:
        raise Exception(f"Could not parse Gemini transcript JSON: {result}")

    parsed = json.loads(result[start:end])

    transcript = parsed.get("transcript", "").strip()
    segment_data = parsed.get("segments", [])

    return transcript, segment_data