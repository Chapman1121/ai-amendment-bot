from connection import ask_ai, ask_ai_multimodal
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

    # Cap to 8 frames evenly spread across the timeline — enough for
    # storytelling context without hitting API token limits.
    if frames:
        step = max(1, len(frames) // 8)
        sampled = frames[::step][:8]
    else:
        sampled = []
    images = [f["base64"] for f in sampled if f.get("base64")]

    frames_index = "\n".join(
        f"- Frame {i+1}: t={f.get('timestamp', 'N/A')}"
        for i, f in enumerate(frames or [])
    ) or "- (no frames provided)"

    prompt = f"""
You are reviewing STORYTELLING clarity and flow in a short-form video.

You may use BOTH the transcript and the sampled frames. Frames cover the
full timeline (opening → end) so you can judge whether the spoken story
matches what is shown on screen.

GROUNDING RULES (READ FIRST):
- Base your judgement ONLY on what is in the transcript and visible in the
  frames provided. Do NOT invent extra context.
- If the transcript and visuals MISMATCH (e.g. caption says one word, the
  visual shows something different), call out the mismatch clearly with the
  timestamp from the frame index — do not guess which one is "right".
- Do NOT critique anything that is not actually in the provided material.

Frame index (timestamps):
{frames_index}

IMPORTANT:
- Always return ONE assessment row, even if storytelling is fine.
- Add issue rows ONLY if there are real clarity, pacing, or visual-vs-spoken
  mismatch problems.
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
        # Multimodal: pass frames so the AI can detect visual-vs-spoken mismatches.
        if images:
            result = ask_ai_multimodal(prompt, images)
        else:
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

    except Exception as e:
        return [{
            "Type": "Storytelling",
            "Location": "Transcript",
            "Snippet": text_part[:120],
            "Issue": f"Storytelling checker failed: {type(e).__name__}: {str(e)[:200]}",
            "Suggestion": "Review the narrative flow manually.",
            "Severity": "Medium",
        }]