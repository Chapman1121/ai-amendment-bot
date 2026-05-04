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


def check_story_clarity(transcript: str):
    text_part = transcript[:1500]

    prompt = f"""
You are evaluating the story clarity and narrative structure of a short-form social media video.

GROUNDING RULES (READ FIRST):
- Base your evaluation ONLY on the transcript provided below.
- Do NOT invent topics, events, or narrative elements not present in the transcript.
- Examples you cite in strengths or improvements MUST reference actual content from the transcript.

FORMAT CONTEXT:
- This is casual short-form content (home tours, vlogs, interviews, lifestyle).
- Natural conversation, informal phrasing, and casual flow are EXPECTED and NORMAL for this format.
- Do NOT penalise the video for not being scripted or polished.

SCORING RULES:
Score 5:
- Very clear story arc — strong opening hook, coherent middle, satisfying close.

Score 4:
- Mostly clear narrative with a recognisable structure even if informal.

Score 3:
- Watchable and followable, but the narrative feels loose or incomplete.
  DEFAULT for any casual interview / vlog / home-tour that is coherent but unscripted.

Score 2:
- Genuinely hard to follow — confusing jumps, missing context, unclear purpose.

Score 1:
- Incoherent or unwatchable — no clear story at all.

IMPORTANT:
- When in doubt between two scores, pick the HIGHER one.
- Only give 2 or 1 if the video is genuinely difficult to follow.
- Do NOT list more than 3 strengths and 3 improvements.
- Keep each point concise (1 sentence).

Return EXACTLY in this JSON format with no markdown, no code fences, no extra text:
{{
  "score": 3,
  "summary": "Short balanced explanation of the narrative structure.",
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
            "summary": parsed.get("summary", "Could not analyze story clarity reliably."),
            "strengths": parsed.get("strengths", []),
            "improvements": parsed.get("improvements", []),
        }

    return {
        "score": 3,
        "summary": "Could not analyze story clarity reliably.",
        "strengths": [],
        "improvements": [],
    }
