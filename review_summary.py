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


def safe_json(result: str):
    try:
        cleaned = _clean_text(result)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(cleaned[start:end])
    except Exception:
        return None



def generate_review_summary(transcript: str):
    text_part = transcript[:1200]

    prompt = f"""
You are a video reviewer.

IMPORTANT:
- ALWAYS return valid JSON
- NEVER return empty output
- NEVER include text outside JSON

Evaluate:

1. Story clarity (1–5)
2. Overall review
3. Retention (Low / Medium / High)
4. Suggestions

SCORING:
- Most interview-style videos = 3
- Only give 4 if structure is strong
- Only give 5 if very polished

Return EXACT JSON:

{{
  "story_score": 3,
  "overall_review": "Balanced explanation here.",
  "retention": "Medium",
  "suggestions": [
    "Suggestion 1",
    "Suggestion 2",
    "Suggestion 3"
  ]
}}

Transcript:
{text_part}
"""

    result = ask_ai(prompt)

    parsed = safe_json(result)

    if parsed:
        return {
            "story_score": parsed.get("story_score", 3),
            "overall_review": parsed.get("overall_review", "Could not generate an overall review reliably."),
            "retention": parsed.get("retention", "Medium"),
            "suggestions": parsed.get("suggestions", [])
        }

    return {
        "story_score": 3,
        "overall_review": "Could not generate an overall review reliably.",
        "retention": "Medium",
        "suggestions": []
    }