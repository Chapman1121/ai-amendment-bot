from connection import ask_ai_multimodal
import json


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
                "Suggestion": suggestion if suggestion else "Make the opening more engaging or attention-grabbing.",
                "Severity": severity,
            })

        return rows

    except Exception:
        return [{
            "Type": "Hook",
            "Location": "Opening",
            "Snippet": fallback_snippet[:120],
            "Issue": "Could not parse AI output",
            "Suggestion": result[:300] if result else "Review hook manually.",
            "Severity": "Medium",
        }]


def check_hook(transcript: str, frames: list, audio_base64: str):
    opening = transcript[:220]

    prompt = f"""
You are reviewing the HOOK (first few seconds) of a short-form video.

You must evaluate the hook using:
1. spoken opening (transcript)
2. opening visuals (frames)
3. audio energy and delivery

Your goal:
Decide whether the opening is strong enough to capture attention.

IMPORTANT:
- Return at most 1 issue.
- Only flag a problem if the hook is clearly weak.
- Consider BOTH what is said and how it feels audiovisually.
- If visuals/audio make the opening dull, you may flag it even if the words are okay.
- If the opening is engaging overall, return no issues.
- The snippet must be an exact phrase from the transcript.
- Do NOT use "..." as a snippet.
- Return ONLY valid JSON.
- Do NOT give generic feedback.
- Every issue must be tied to a specific phrase, moment, visual pattern, or audio problem.
- Suggestions must be concrete and actionable.
- Avoid vague phrases like "improve engagement" or "make it better".

FORMAT:
{{
  "issues": [
    {{
      "snippet": "exact phrase",
      "issue": "specific hook problem",
      "suggestion": "specific improvement",
      "severity": "Low | Medium | High"
    }}
  ]
}}

If no issues:
{{"issues":[]}}

Transcript:
{opening}
"""

    images = [f["base64"] for f in frames[:2]] if frames else []

    try:
        result = ask_ai_multimodal(prompt, images, audio_base64)

        if not result:
            return []

        return safe_json_parse(result.strip(), opening)

    except Exception:
        return []