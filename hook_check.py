from connection import ask_ai_multimodal
import json


def safe_json_parse(result: str, fallback_snippet: str):
    try:
        start = result.find("{")
        end = result.rfind("}") + 1

        if start == -1 or end == 0:
            return [{
                "Type": "Hook",
                "Location": "Opening",
                "Snippet": fallback_snippet[:120],
                "Issue": "Opening hook could not be evaluated reliably.",
                "Suggestion": "Review the first few seconds manually for attention, clarity, and energy.",
                "Severity": "Medium",
            }]

        cleaned = result[start:end]
        data = json.loads(cleaned)

        rows = []
        seen = set()
        allowed_severities = {"Low", "Medium", "High"}

        assessment = data.get("assessment", {}) or {}
        a_snippet = str(assessment.get("snippet", "")).strip() or fallback_snippet[:120]
        a_issue = str(assessment.get("issue", "")).strip() or "Opening hook reviewed."
        a_suggestion = str(assessment.get("suggestion", "")).strip() or "Keep the opening clear, engaging, and easy to follow."
        a_severity = str(assessment.get("severity", "Low")).strip().title()

        if a_severity not in allowed_severities:
            a_severity = "Low"

        rows.append({
            "Type": "Hook",
            "Location": "Opening",
            "Snippet": a_snippet[:120],
            "Issue": a_issue,
            "Suggestion": a_suggestion,
            "Severity": a_severity,
        })
        seen.add((a_snippet.lower(), a_issue.lower()))

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
                "Type": "Hook",
                "Location": "Opening",
                "Snippet": snippet[:120],
                "Issue": issue,
                "Suggestion": suggestion if suggestion else "Strengthen the first few seconds with a clearer or more engaging opening.",
                "Severity": severity,
            })

        return rows

    except Exception:
        return [{
            "Type": "Hook",
            "Location": "Opening",
            "Snippet": fallback_snippet[:120],
            "Issue": "Could not parse hook evaluation output.",
            "Suggestion": "Review the opening manually.",
            "Severity": "Medium",
        }]


def check_hook(transcript: str, frames: list, audio_base64: str):
    opening = transcript[:220]
    images = [f["base64"] for f in frames[:2]] if frames else []

    prompt = f"""
You are reviewing the HOOK (first few seconds) of a short-form video.

You must evaluate the hook using:
1. spoken opening (transcript)
2. opening visuals (frames)
3. audio energy and delivery

IMPORTANT:
- Always return ONE assessment row, even if the hook is fine.
- If there are additional specific hook problems, return them under "issues".
- Be practical and balanced.
- Consider both the words and the audiovisual impact.
- The assessment should describe how strong the opening feels overall.
- The snippet should be an exact phrase from the opening transcript when possible.
- Return ONLY valid JSON.

FORMAT:
{{
  "assessment": {{
    "snippet": "exact opening phrase",
    "issue": "overall evaluation of the opening hook",
    "suggestion": "overall improvement suggestion",
    "severity": "Low | Medium | High"
  }},
  "issues": [
    {{
      "snippet": "exact phrase",
      "issue": "specific hook problem",
      "suggestion": "specific improvement",
      "severity": "Low | Medium | High"
    }}
  ]
}}

Transcript:
{opening}
"""

    try:
        result = ask_ai_multimodal(prompt, images, None)
        if not result:
            return [{
                "Type": "Hook",
                "Location": "Opening",
                "Snippet": opening[:120],
                "Issue": "Hook evaluation returned no result.",
                "Suggestion": "Review the first few seconds manually.",
                "Severity": "Medium",
            }]
        return safe_json_parse(result.strip(), opening)
    except Exception:
        return [{
            "Type": "Hook",
            "Location": "Opening",
            "Snippet": opening[:120],
            "Issue": "Hook checker failed during multimodal analysis.",
            "Suggestion": "Review the opening manually or inspect the multimodal request.",
            "Severity": "Medium",
        }]