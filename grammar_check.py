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

        if start == -1 or end <= start:
            return []

        parsed_text = result[start:end]
        data = json.loads(parsed_text)

        rows = []
        seen = set()
        allowed_severities = {"Low", "Medium", "High"}

        for item in data.get("issues", []):
            snippet = str(item.get("snippet", "")).strip()
            issue = str(item.get("issue", "")).strip()
            suggestion = str(item.get("suggestion", "")).strip()
            severity = str(item.get("severity", "Medium")).strip().title()

            if not issue:
                continue

            if severity not in allowed_severities:
                severity = "Medium"

            if not snippet or snippet in {"...", ".", ".."}:
                snippet = fallback_snippet[:120]

            key = (snippet.lower(), issue.lower())
            if key in seen:
                continue
            seen.add(key)

            rows.append({
                "Type": "Grammar",
                "Location": "Transcript",
                "Snippet": snippet[:120],
                "Issue": issue,
                "Suggestion": suggestion if suggestion else "Review only if the sentence is genuinely unclear.",
                "Severity": severity
            })

        return rows

    except Exception:
        return [{
            "Type": "Grammar",
            "Location": "Transcript",
            "Snippet": fallback_snippet[:120],
            "Issue": "Could not parse AI output",
            "Suggestion": result[:300],
            "Severity": "Medium"
        }]


def check_grammar(transcript: str, glossary: list[str] | None = None):
    text_part = transcript[:900]

    # Build glossary note if we have one
    glossary_note = ""
    if glossary:
        glossary_note = f"""
KNOWN NAMES AND BRANDS — DO NOT FLAG THESE AS GRAMMAR ISSUES:
{", ".join(glossary)}

These are real brand names, product names, or proper nouns used intentionally in this video.
Treat them as correct regardless of how unusual they look.
"""

    prompt = f"""
You're a Koocester editor checking subtitle grammar.

This is spoken SG/MY English — casual grammar is totally fine. The bar is simple: would a viewer reading this subtitle actually misunderstand what's being said?

DON'T flag:
- Casual phrasing ("lah", "mah", "lor", "can or not")
- Missing articles ("I go shop" is fine — it's conversational)
- Informal SG/MY sentence structure that's still clear
- Anything understandable even if not "textbook" English
{glossary_note}
ONLY flag if:
- The sentence is confusing and the viewer won't know what was meant
- The grammar is so broken it looks like a transcription error

Max 2–3 flags. If it's clean, return an empty list — don't go looking for problems that aren't there.

Return ONLY valid JSON:
{{
  "issues": [
    {{
      "type": "Grammar",
      "location": "Transcript",
      "snippet": "exact phrase from transcript",
      "issue": "why this will confuse the viewer",
      "suggestion": "fixed version",
      "severity": "Low"
    }}
  ]
}}

If clean: {{"issues":[]}}

Transcript:
{text_part}
"""

    result = ask_ai(prompt).strip()
    return safe_json_parse(result, text_part)
