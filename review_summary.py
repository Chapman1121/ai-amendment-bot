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

GROUNDING RULES (READ FIRST):
- Base your review ONLY on the transcript provided below.
- Do NOT invent topics, products, or events not present in the transcript.
- Do NOT speculate about visuals you have not seen.
- Suggestions must be actionable based on what is actually in the transcript.

IMPORTANT:
- ALWAYS return valid JSON
- NEVER return empty output
- NEVER include text outside JSON

Evaluate:

1. Overall review — a balanced 2–3 sentence summary of the video as a whole
2. Retention (Low / Medium / High)
3. Top suggestions for improvement

RETENTION RULES:
- Default to "Medium" for any video that is watchable and has a clear topic
- Only use "Low" if the video is genuinely hard to follow or has major structural problems
- Use "High" only if the hook and pacing are actively strong

Return EXACT JSON:

{{
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
            "overall_review": parsed.get("overall_review", "Could not generate an overall review reliably."),
            "retention": parsed.get("retention", "Medium"),
            "suggestions": parsed.get("suggestions", [])
        }

    return {
        "overall_review": "Could not generate an overall review reliably.",
        "retention": "Medium",
        "suggestions": []
    }