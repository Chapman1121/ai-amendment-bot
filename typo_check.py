import json
from connection import ask_ai

def _clean_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    return text


def safe_json_parse(result: str, fallback_snippet: str):
    try:
        start = result.find("{")
        end = result.rfind("}") + 1

        if start == -1 or end == 0:
            return []

        result = result[start:end]
        data = json.loads(result)

        rows = []
        seen = set()

        for item in data.get("issues", []):
            snippet = item.get("snippet", "").strip()
            issue = item.get("issue", "").strip()
            suggestion = item.get("suggestion", "").strip()
            severity = item.get("severity", "Low").strip()

            if not issue:
                continue

            if not snippet or snippet in {"...", ".", ".."}:
                snippet = fallback_snippet[:120]

            key = (snippet.lower(), issue.lower())
            if key in seen:
                continue
            seen.add(key)

            rows.append({
                "Type": "Typos",
                "Location": "Transcript",
                "Snippet": snippet[:120],
                "Issue": issue,
                "Suggestion": suggestion if suggestion else "Review spelling manually.",
                "Severity": severity
            })

        return rows

    except Exception:
        return [{
            "Type": "Typos",
            "Location": "Transcript",
            "Snippet": fallback_snippet[:120],
            "Issue": "Could not parse AI output",
            "Suggestion": result[:300],
            "Severity": "Medium"
        }]


def check_typos(transcript: str, glossary: list[str] | None = None):
    text_part = transcript[:500]

    # Build glossary note if we have one
    glossary_note = ""
    if glossary:
        glossary_note = f"""
KNOWN NAMES AND BRANDS — DO NOT FLAG THESE AS TYPOS:
{", ".join(glossary)}

These are real brand names, product names, or proper nouns that appear intentionally in this video.
"""

    prompt = f"""
You are reviewing a transcript for spelling mistakes and typos only.

Your task:
- identify only clear typos or spelling mistakes
- do NOT flag grammar issues
- do NOT flag storytelling issues
- do NOT flag awkward wording
- do NOT flag names, brands, or place names unless they are clearly misspelled in context
- be careful with accented English and transcript-style speech
- only report obvious typo-like errors
{glossary_note}
IMPORTANT:
- Return ONLY valid JSON
- Do NOT include text before or after JSON
- The snippet must be an exact phrase copied from the transcript
- Do NOT use "..." as a snippet

Return in this format:
{{
  "issues": [
    {{
      "type": "Typos",
      "location": "Transcript",
      "snippet": "exact phrase",
      "issue": "specific typo or spelling issue",
      "suggestion": "correct spelling",
      "severity": "Low"
    }}
  ]
}}

If there are no typo issues, return:
{{"issues":[]}}

Transcript:
{text_part}
"""

    result = ask_ai(prompt).strip()
    return safe_json_parse(result, text_part)