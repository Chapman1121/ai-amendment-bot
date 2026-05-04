import os

from typing import Any, Dict, List, Optional

import requests
import streamlit as st

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_AUDIO_MODEL = "gpt-4o-audio-preview"
OPENAI_TRANSCRIBE_MODEL = "whisper-1"

RESPONSES_URL = "https://api.openai.com/v1/responses"
CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
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


def _post_responses(content: List[Dict[str, Any]], model: Optional[str] = None) -> str:
    payload = {
        "model": model or OPENAI_MODEL,
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


def ask_ai_multimodal(prompt: str, images_base64: Optional[list] = None) -> str:
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


def _post_chat_completions(messages: List[Dict[str, Any]], model: str) -> str:
    payload = {
        "model": model,
        "messages": messages,
    }
    response = requests.post(
        CHAT_COMPLETIONS_URL,
        headers={**_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=600,
    )
    if not response.ok:
        raise Exception(
            f"OpenAI Chat Completions error {response.status_code}: {response.text[:1200]}"
        )
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise Exception(f"Unexpected chat completions response: {str(data)[:1200]}") from exc


def ask_ai_audio(prompt: str, audio_base64: str) -> str:
    """Send prompt + audio to gpt-4o-audio-preview via Chat Completions."""
    return _post_chat_completions(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_base64,
                            "format": "mp3",
                        },
                    },
                ],
            }
        ],
        model=OPENAI_AUDIO_MODEL,
    )


def transcribe_audio_file(audio_path: str, hint_words: Optional[str] = None) -> Dict[str, Any]:
    with open(audio_path, "rb") as f:
        files = {
            "file": (os.path.basename(audio_path), f, "audio/mpeg"),
        }
        base_prompt = (
            "The speaker is using Singaporean or Malaysian accented English. "
            "Transcribe in English only. "
            "Do not translate into Malay. "
            "Preserve natural spoken phrasing and names as accurately as possible."
        )
        whisper_prompt = base_prompt
        if hint_words:
            whisper_prompt += f" Key words in this video: {hint_words}."

        data = {
            "model": OPENAI_TRANSCRIBE_MODEL,
            "response_format": "verbose_json",
            "language": "en",
            "prompt": whisper_prompt,
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
