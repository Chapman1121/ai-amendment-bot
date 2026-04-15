from connection import ask_ai
import json

def _clean_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    return text



def safe_json_parse(result: str):
    try:
        cleaned = _clean_text(result)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1

        if start == -1 or end == 0:
            return None

        return json.loads(cleaned[start:end])
    except Exception:
        return None



def check_information_clarity(transcript: str):
    text_part = transcript[:1500]

    prompt = f"""
You are evaluating how clearly information is communicated in a video.

IMPORTANT:
- Return ONLY valid JSON
- Do NOT include markdown
- Do NOT include code fences
- Do NOT include any text before or after the JSON
- This is spoken English (SG/MY style allowed)
- Do NOT penalize casual grammar if understandable
- Focus ONLY on whether the viewer understands the message

SCORING RULES:

Score 5:
- very clear, easy to follow, no confusion

Score 4:
- mostly clear with minor gaps

Score 3:
- understandable but slightly scattered

Score 2:
- confusing in parts

Score 1:
- hard to understand

IMPORTANT:
- If ideas jump too quickly → reduce score
- If message is not clearly structured → do NOT give 4 or 5

Return EXACTLY in this JSON format:
{{
  "score": 3,
  "summary": "Short realistic explanation.",
  "strengths": [
    "Strength 1",
    "Strength 2"
  ],
  "improvements": [
    "Improvement 1",
    "Improvement 2"
  ]
}}

Transcript:
{text_part}
"""

    result = ask_ai(prompt)
    parsed = safe_json_parse(result)

    if parsed:
        return {
            "score": parsed.get("score", 3),
            "summary": parsed.get("summary", "Could not analyze information clarity reliably."),
            "strengths": parsed.get("strengths", []),
            "improvements": parsed.get("improvements", []),
        }

    return {
        "score": 3,
        "summary": "Could not analyze information clarity reliably.",
        "strengths": [],
        "improvements": []
    }