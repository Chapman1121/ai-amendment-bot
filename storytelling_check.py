import json
from connection import ask_ai_multimodal


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

            if not issue:
                continue

            if not snippet or snippet in {"...", ".", ".."}:
                snippet = fallback_snippet[:120]

            key = (snippet, issue)
            if key in seen:
                continue
            seen.add(key)

            rows.append({
                "Type": "Storytelling",
                "Location": "Transcript",
                "Snippet": snippet[:120],
                "Issue": issue,
                "Suggestion": suggestion if suggestion else "Improve narrative flow",
                "Severity": "Medium",
            })

        return rows

    except Exception:
        return [{
            "Type": "Storytelling",
            "Location": "Transcript",
            "Snippet": fallback_snippet[:120],
            "Issue": "Could not parse AI output",
            "Suggestion": result[:300],
            "Severity": "Medium",
        }]


def check_storytelling(transcript: str, frames: list, audio_base64: str):
    text_part = transcript[:900]

    prompt = f"""
You are reviewing a short-form VIDEO for storytelling clarity.

IMPORTANT CONTEXT:
- This is a natural conversation or interview, not a scripted speech.
- Small topic shifts are normal.
- Casual speaking style is expected.

You must evaluate storytelling using:
1. transcript clarity
2. whether the visuals support what is being said
3. whether pacing, edit flow, and audiovisual continuity help or hurt understanding

YOUR TASK:
Determine if the viewer would feel CONFUSED while watching.

ONLY FLAG storytelling issues IF:
- the audience would struggle to follow the idea
- the explanation is unclear or incomplete
- visuals do not support the point being made
- pacing or cuts make the flow harder to follow
- the speaker leaves a thought unfinished in a confusing way

DO NOT FLAG:
- natural topic changes
- casual transitions
- conversational jumps that still make sense
- minor flow imperfections
- simple interview-style visuals unless they clearly hurt understanding

THINK LIKE A VIEWER:
- Would someone watching this feel lost?
- Or is it still easy enough to follow?

IMPORTANT:
- Return ONLY valid JSON
- Be strict and selective
- No generic feedback

FORMAT:
{{
  "issues": [
    {{
      "type": "Storytelling",
      "location": "Transcript",
      "snippet": "exact phrase",
      "issue": "why this part is confusing to a viewer",
      "suggestion": "how to improve clarity",
      "severity": "Medium"
    }}
  ]
}}

If flow is clear:
{{"issues":[]}}

Transcript:
{text_part}
"""

    images = [f["base64"] for f in frames[:3]] if frames else []

    try:
        result = ask_ai_multimodal(prompt, images, audio_base64)

        if not result:
            return []

        return safe_json_parse(result.strip(), text_part)

    except Exception:
        return []