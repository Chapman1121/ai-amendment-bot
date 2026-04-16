from connection import ask_ai
import json


def safe_json_parse(result: str, fallback_snippet: str):
    try:
        start = result.find("{")
        end = result.rfind("}") + 1

        if start == -1 or end == 0:
            return [{
                "Type": "Storytelling",
                "Location": "Transcript",
                "Snippet": fallback_snippet[:120],
                "Issue": "Storytelling flow could not be evaluated reliably.",
                "Suggestion": "Review whether the narrative is easy to follow from beginning to end.",
                "Severity": "Medium",
            }]

        cleaned = result[start:end]
        data = json.loads(cleaned)

        rows = []
        seen = set()
        allowed_severities = {"Low", "Medium", "High"}

        # ✅ ALWAYS ADD ASSESSMENT ROW
        assessment = data.get("assessment", {}) or {}
        a_snippet = str(assessment.get("snippet", "")).strip() or fallback_snippet[:120]
        a_issue = str(assessment.get("issue", "")).strip() or "Storytelling flow reviewed."
        a_suggestion = str(assessment.get("suggestion", "")).strip() or "Keep the story progression clear and easy to follow."
        a_severity = str(assessment.get("severity", "Low")).strip().title()

        if a_severity not in allowed_severities:
            a_severity = "Low"

        rows.append({
            "Type": "Storytelling",
            "Location": "Transcript",
            "Snippet": a_snippet[:120],
            "Issue": a_issue,
            "Suggestion": a_suggestion,
            "Severity": a_severity,
        })
        seen.add((a_snippet.lower(), a_issue.lower()))

        # ✅ ADD ISSUE ROWS IF ANY
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
                "Type": "Storytelling",
                "Location": "Transcript",
                "Snippet": snippet[:120],
                "Issue": issue,
                "Suggestion": suggestion if suggestion else "Improve the flow so the viewer can follow the idea more easily.",
                "Severity": severity,
            })

        return rows

    except Exception:
        return [{
            "Type": "Storytelling",
            "Location": "Transcript",
            "Snippet": fallback_snippet[:120],
            "Issue": "Could not parse storytelling evaluation output.",
            "Suggestion": "Review the narrative flow manually.",
            "Severity": "Medium",
        }]


def check_storytelling(transcript: str, frames: list, audio_base64: str):
    text_part = transcript[:900]

    prompt = f"""
You are reviewing STORYTELLING clarity in a short-form video.

IMPORTANT:
- Use ONLY the transcript.
- Do NOT assume visuals or audio.
- Always return ONE assessment row.
- Add issue rows ONLY if there are real clarity problems.
- Be realistic: this may be conversational content.

FORMAT:
{{
  "assessment": {{
    "snippet": "exact phrase",
    "issue": "overall evaluation of storytelling clarity and flow",
    "suggestion": "overall improvement suggestion",
    "severity": "Low | Medium | High"
  }},
  "issues": [
    {{
      "snippet": "exact phrase",
      "issue": "specific storytelling problem",
      "suggestion": "specific improvement",
      "severity": "Low | Medium | High"
    }}
  ]
}}

Transcript:
{text_part}
"""

    try:
        result = ask_ai(prompt)

        if not result:
            return [{
                "Type": "Storytelling",
                "Location": "Transcript",
                "Snippet": text_part[:120],
                "Issue": "Storytelling evaluation returned no result.",
                "Suggestion": "Review the flow manually.",
                "Severity": "Medium",
            }]

        return safe_json_parse(result.strip(), text_part)

    except Exception:
        return [{
            "Type": "Storytelling",
            "Location": "Transcript",
            "Snippet": text_part[:120],
            "Issue": "Storytelling checker failed.",
            "Suggestion": "Review the narrative flow manually or inspect the AI response.",
            "Severity": "Medium",
        }]