import json
from connection import ask_ai_multimodal


def safe_json_parse(result: str, fallback_snippet: str):
    try:
        start = result.find("{")
        end = result.rfind("}") + 1

        if start == -1 or end == 0:
            return [{
                "Type": "Required Elements",
                "Location": "Video",
                "Snippet": fallback_snippet[:120],
                "Issue": "Required elements could not be evaluated reliably.",
                "Suggestion": "Review CTA presence, ending action, and branding manually.",
                "Severity": "Medium",
            }]

        cleaned = result[start:end]
        data = json.loads(cleaned)

        rows = []
        seen = set()
        allowed_severities = {"Low", "Medium", "High"}

        assessment = data.get("assessment", {}) or {}
        a_location = str(assessment.get("location", "Video")).strip() or "Video"
        a_snippet = str(assessment.get("snippet", "")).strip() or fallback_snippet[:120]
        a_issue = str(assessment.get("issue", "")).strip() or "Required elements reviewed."
        a_suggestion = str(assessment.get("suggestion", "")).strip() or "Keep CTAs and branding clear enough for viewers to notice."
        a_severity = str(assessment.get("severity", "Low")).strip().title()

        if a_severity not in allowed_severities:
            a_severity = "Low"

        rows.append({
            "Type": "Required Elements",
            "Location": a_location,
            "Snippet": a_snippet[:120],
            "Issue": a_issue,
            "Suggestion": a_suggestion,
            "Severity": a_severity,
        })
        seen.add((a_location.lower(), a_snippet.lower(), a_issue.lower()))

        for item in data.get("issues", []):
            location = str(item.get("location", "Video")).strip() or "Video"
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

            key = (location.lower(), snippet.lower(), issue.lower())
            if key in seen:
                continue
            seen.add(key)

            rows.append({
                "Type": "Required Elements",
                "Location": location,
                "Snippet": snippet[:120],
                "Issue": issue,
                "Suggestion": suggestion if suggestion else "Make the CTA, ending action, or branding clearer to viewers.",
                "Severity": severity,
            })

        return rows

    except Exception:
        return [{
            "Type": "Required Elements",
            "Location": "Video",
            "Snippet": fallback_snippet[:120],
            "Issue": "Could not parse required elements evaluation output.",
            "Suggestion": "Review CTA and branding manually.",
            "Severity": "Medium",
        }]


def check_required_elements(transcript: str, frames: list, audio_base64: str):
    text_part = transcript[:700]
    images = [f["base64"] for f in frames] if frames else []

    prompt = f"""
You are reviewing REQUIRED ELEMENTS in a short-form edited video.

Use:
1. transcript context
2. visual frames
3. audio context

Evaluate whether the video clearly includes:
- a noticeable CTA
- a mid-video CTA if appropriate
- an ending CTA or closing action
- branding, identity, or watermark if relevant

IMPORTANT:
- Always return ONE assessment row, even if the required elements are fine.
- If there are additional specific problems, return them under "issues".
- Be realistic and viewer-based, not just keyword-based.
- Return ONLY valid JSON.

FORMAT:
{{
  "assessment": {{
    "location": "Opening | Middle | Ending | Video",
    "snippet": "exact phrase or short visible text reference",
    "issue": "overall evaluation of CTA / branding / ending clarity",
    "suggestion": "overall improvement suggestion",
    "severity": "Low | Medium | High"
  }},
  "issues": [
    {{
      "location": "Opening | Middle | Ending | Video",
      "snippet": "exact phrase or short visible text reference",
      "issue": "specific required element problem",
      "suggestion": "specific improvement",
      "severity": "Low | Medium | High"
    }}
  ]
}}

Transcript:
{text_part}
"""

    try:
        result = ask_ai_multimodal(prompt, images, None)
        if not result:
            return [{
                "Type": "Required Elements",
                "Location": "Video",
                "Snippet": text_part[:120],
                "Issue": "Required elements evaluation returned no result.",
                "Suggestion": "Review CTA and branding manually.",
                "Severity": "Medium",
            }]
        return safe_json_parse(result.strip(), text_part)
    except Exception:
        return [{
            "Type": "Required Elements",
            "Location": "Video",
            "Snippet": text_part[:120],
            "Issue": "Required elements checker failed during multimodal analysis.",
            "Suggestion": "Review CTA and branding manually or inspect the multimodal request.",
            "Severity": "Medium",
        }]