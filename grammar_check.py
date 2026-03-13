import json
from connection import ask_ai


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
            severity = item.get("severity", "Medium").strip()

            if not issue:
                continue

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
                "Suggestion": suggestion if suggestion else "Review grammar manually.",
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


def check_grammar(transcript: str):
    text_part = transcript[:600]

    prompt = f"""
You are reviewing a transcript for grammar issues only.

Your task:
- identify only clear grammar mistakes
- do NOT flag spelling or typo issues
- do NOT flag storytelling issues
- do NOT flag hook issues
- do NOT flag names, brand names, or place names
- be careful with spoken English and accented English
- only report grammar issues that are clearly wrong in transcript/caption form

Examples of grammar issues:
- subject-verb disagreement
- incorrect tense usage
- missing function words that make the sentence grammatically broken
- sentence structure that is clearly grammatically incorrect

IMPORTANT:
- Return ONLY valid JSON
- Do NOT include text before or after JSON
- The snippet must be an exact phrase copied from the transcript
- Do NOT use "..." as a snippet
- Do not report more than necessary; only include real grammar issues

Return in this format:
{{
  "issues": [
    {{
      "type": "Grammar",
      "location": "Transcript",
      "snippet": "exact phrase",
      "issue": "specific grammar problem",
      "suggestion": "corrected version or improvement",
      "severity": "Medium"
    }}
  ]
}}

If there are no grammar issues, return:
{{"issues":[]}}

Transcript:
{text_part}
"""

    result = ask_ai(prompt).strip()
    return safe_json_parse(result, text_part)