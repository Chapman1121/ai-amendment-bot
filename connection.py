import os
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

OPENAI_MODEL = os.getenv("OPENAI_MODEL") or st.secrets.get("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL") or st.secrets.get("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

RESPONSES_URL = "https://api.openai.com/v1/responses"
TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"


def _headers() -> Dict[str, str]:
    if not OPENAI_API_KEY:
        raise Exception("Missing OPENAI_API_KEY")
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }


def _extract_response_text(result: Dict[str, Any]) -> str:
    output_text = result.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    texts: List[str] = []

    for item in result.get("output", []) or []:
        for content in item.get("content", []) or []:
            ctype = content.get("type")
            if ctype in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    texts.append(text)
                elif isinstance(text, dict):
                    maybe = text.get("value") or text.get("text")
                    if isinstance(maybe, str):
                        texts.append(maybe)

    final_text = "\n".join(t for t in texts if t).strip()
    if not final_text:
        raise Exception(f"OpenAI returned no text content: {str(result)[:1200]}")
    return final_text


def _post_responses(content: List[Dict[str, Any]]) -> str:
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
    }

    response = requests.post(
        RESPONSES_URL,
        headers={**_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=600,
    )

    if not response.ok:
        raise Exception(f"OpenAI Responses error {response.status_code}: {response.text[:1200]}")

    return _extract_response_text(response.json())


def ask_ai(prompt: str) -> str:
    return _post_responses([
        {
            "type": "input_text",
            "text": prompt,
        }
    ])


def ask_ai_images(prompt: str, images_base64: list) -> str:
    content: List[Dict[str, Any]] = [
        {
            "type": "input_text",
            "text": prompt,
        }
    ]

    for img in images_base64 or []:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{img}",
            }
        )

    return _post_responses(content)


def ask_ai_multimodal(
    prompt: str,
    images_base64: Optional[list] = None,
    audio_base64: Optional[str] = None,
) -> str:
    content: List[Dict[str, Any]] = [
        {
            "type": "input_text",
            "text": prompt,
        }
    ]

    for img in images_base64 or []:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{img}",
            }
        )

    if audio_base64:
        content.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": audio_base64,
                    "format": "mp3",
                },
            }
        )

    return _post_responses(content)


def ask_ai_audio(prompt: str, audio_base64: str) -> str:
    return _post_responses(
        [
            {
                "type": "input_text",
                "text": prompt,
            },
            {
                "type": "input_audio",
                "input_audio": {
                    "data": audio_base64,
                    "format": "mp3",
                },
            },
        ]
    )


def transcribe_audio_file(audio_path: str) -> Dict[str, Any]:
    with open(audio_path, "rb") as f:
        files = {
            "file": (os.path.basename(audio_path), f, "audio/mpeg"),
        }
        data = {
            "model": OPENAI_TRANSCRIBE_MODEL,
            "response_format": "verbose_json",
            "language": "en",
            "prompt": (
                "The speaker is using Singaporean or Malaysian accented English. "
                "Transcribe in English only. "
                "Do not translate into Malay. "
                "Preserve natural spoken phrasing and names as accurately as possible."
            ),
        }

        response = requests.post(
            TRANSCRIPTIONS_URL,
            headers=_headers(),
            files=files,
            data=data,
            timeout=600,
        )

    if not response.ok:
        raise Exception(f"OpenAI transcription error {response.status_code}: {response.text[:1200]}")

    result = response.json()
    if not isinstance(result, dict):
        raise Exception(f"Unexpected transcription response: {str(result)[:1200]}")
    return result
