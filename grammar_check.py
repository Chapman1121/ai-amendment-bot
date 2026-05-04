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
You are reviewing a RAW interview transcript from a short-form video.

IMPORTANT CONTEXT:
- This is spoken English, not written English.
- The speaker may be from Singapore or Malaysia.
- Natural conversational grammar is acceptable if the meaning is clear.
{glossary_note}
YOUR TASK:
- ONLY flag grammar issues that make the sentence:
  1. hard to understand, OR
  2. clearly incorrect to the point it sounds broken

DO NOT FLAG:
- casual spoken phrasing
- missing small words (e.g., "I go shop" instead of "I go to the shop")
- common conversational grammar used in SG/MY speech
- stylistic or informal speech
- sentences that are understandable even if not perfect
- any word from the known names and brands list above

ONLY FLAG IF:
- the listener might misunderstand the sentence
- the grammar is noticeably broken or confusing

EXAMPLES:

DO NOT FLAG:
- "Are you sell PS5?" → understandable in conversation
- "every day I cycling" → acceptable spoken phrasing

FLAG:
- "He go yesterday tomorrow" → unclear meaning
- "This thing is not make sense doing" → broken structure

IMPORTANT:
- Return ONLY valid JSON
- Do NOT include any explanation outside JSON
- Max 2–3 issues only (be selective)
- The snippet must be exact text from transcript
- Do NOT use "..."

FORMAT:
{{
  "issues": [
    {{
      "type": "Grammar",
      "location": "Transcript",
      "snippet": "exact phrase",
      "issue": "clear explanation of why it is confusing or broken",
      "suggestion": "improved version",
      "severity": "Low" | "Medium"
    }}
  ]
}}

If no real issues:
{{"issues":[]}}

Transcript:
{text_part}
"""

    result = ask_ai(prompt).strip()
    return safe_json_parse(result, text_part)
