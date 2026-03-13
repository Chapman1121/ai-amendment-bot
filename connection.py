import requests
import streamlit as st
API_KEY = "GEMINI_API_KEY"


def ask_ai(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
    data = {
        "contents":[

            {
                "parts": [
                    {"text" : prompt}
                ]
            }
        ]
    }
       

    response = requests.post(url, json=data, timeout=600)
    result = response.json()

    if "candidates" not in result:
        raise Exception(f"Gemini error: {result}")

    return result["candidates"][0]["content"]["parts"][0]["text"].strip()

def ask_ai_audio(prompt: str, audio_base64: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "audio/mpeg",
                            "data": audio_base64
                        }
                    }
                ]
            }
        ]
    }

    response = requests.post(url, json=data, timeout=600)
    result = response.json()

    if "candidates" not in result:
        raise Exception(f"Gemini audio error: {result}")

    return result["candidates"][0]["content"]["parts"][0]["text"]
