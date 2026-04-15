import json
from connection import ask_ai_multimodal


def safe_json_parse(result: str, fallback_snippet: str):
    try:
        start = result.find("{")
        end = result.rfind("}") + 1

        if start == -1 or end == 0:
            return []

        cleaned = result[start:end]
        data = json.loads(cleaned)

        rows = []
        seen = set()
        allowed_severities = {"Low", "Medium", "High"}

        for item in data.get("issues", []):
            location = str(item.get("location", "Video")).strip()
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
                "Suggestion": suggestion if suggestion else "Improve the visibility and clarity of the required element.",
                "Severity": severity,
            })

        return rows

    except Exception:
        return [{
            "Type": "Required Elements",
            "Location": "Video",
            "Snippet": fallback_snippet[:120],
            "Issue": "Could not parse AI output",
            "Suggestion": result[:300] if result else "Review required elements manually.",
            "Severity": "Medium",
        }]


def check_required_elements(transcript: str, frames: list, audio_base64: str):
    text_part = transcript[:700]

    prompt = f"""
You are reviewing REQUIRED ELEMENTS in a short-form edited video.

You must evaluate the video using:
1. transcript context
2. visual frames
3. audio context

Your job is to decide whether the video clearly includes the following elements:

- a noticeable call to action (CTA)
- a mid-video CTA if appropriate
- an ending CTA or closing action
- branding, identity, or watermark if relevant

IMPORTANT:
- Do NOT rely only on keyword matching.
- Judge the video like a real viewer would.
- A CTA counts only if it is clear enough to be noticed.
- A spoken CTA, visual CTA, or combined CTA can all count.
- If a CTA exists but is weak, unclear, badly placed, or easy to miss, you may flag it.
- Branding/watermark should only be flagged if its absence or weakness is genuinely a problem.
- Be selective.
- Return ONLY valid JSON.
- Do NOT include any text outside the JSON.
 Do NOT give generic feedback.
- Every issue must be tied to a specific phrase, moment, visual pattern, or audio problem.
- Suggestions must be concrete and actionable.

FORMAT:
{{
  "issues": [
    {{
      "location": "Middle | Ending | Video | Opening",
      "snippet": "exact phrase from transcript if relevant, otherwise short visible text reference",
      "issue": "specific required element problem",
      "suggestion": "specific improvement",
      "severity": "Low | Medium | High"
    }}
  ]
}}

If all required elements are handled well, return:
{{"issues":[]}}

Transcript:
{text_part}
"""

    images = [f["base64"] for f in frames] if frames else []

    try:
        result = ask_ai_multimodal(prompt, images, audio_base64)

        if not result:
            return []

        return safe_json_parse(result.strip(), text_part)

    except Exception:
        return []