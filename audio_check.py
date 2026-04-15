import base64
import json
import subprocess
import tempfile
import os
from connection import ask_ai_audio


def audio_file_to_base64(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def safe_json_parse(result: str):
    try:
        start = result.find("{")
        end = result.rfind("}") + 1

        if start == -1 or end == 0:
            return None

        return json.loads(result[start:end])
    except:
        return None


def get_ffmpeg_audio_stats(audio_path: str):
    """
    Uses ffmpeg volumedetect to extract basic loudness stats.
    """
    cmd = [
        "ffmpeg",
        "-i", audio_path,
        "-af", "volumedetect",
        "-f", "null",
        os.devnull
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    output = result.stderr

    mean_volume = None
    max_volume = None

    for line in output.splitlines():
        line = line.strip()
        if "mean_volume:" in line:
            try:
                mean_volume = float(line.split("mean_volume:")[1].split(" dB")[0].strip())
            except:
                pass
        if "max_volume:" in line:
            try:
                max_volume = float(line.split("max_volume:")[1].split(" dB")[0].strip())
            except:
                pass

    return {
        "mean_volume": mean_volume,
        "max_volume": max_volume
    }


def fallback_audio_review(audio_path: str):
    stats = get_ffmpeg_audio_stats(audio_path)

    mean_vol = stats.get("mean_volume")
    max_vol = stats.get("max_volume")

    score = 3
    strengths = []
    issues = []
    suggestions = []

    if mean_vol is not None:
        if mean_vol < -30:
            score = 2
            issues.append("Overall audio level seems quite low.")
            suggestions.append("Increase vocal loudness or overall mix level.")
        elif -24 <= mean_vol <= -12:
            strengths.append("Overall loudness appears reasonably balanced.")
        elif mean_vol > -10:
            score = 2
            issues.append("Overall audio may be too loud or overly compressed.")
            suggestions.append("Reduce loudness slightly and check for harshness.")

    if max_vol is not None:
        if max_vol >= -1:
            issues.append("Audio peaks are very close to clipping.")
            suggestions.append("Lower peak levels slightly to avoid distortion.")
            score = min(score, 2)
        elif max_vol <= -6:
            strengths.append("Peak levels appear controlled.")

    if not strengths and not issues:
        strengths.append("Basic audio signal could be processed.")
        suggestions.append("Review voice clarity and SFX balance manually if needed.")

    summary = "Audio fallback review generated from technical signal checks."
    if issues:
        summary += " Some mix issues may need manual review."
    else:
        summary += " No obvious loudness problem was detected."

    return {
        "score": score,
        "summary": summary,
        "strengths": strengths,
        "issues": issues,
        "suggestions": suggestions,
        "timestamp_notes": []
    }


def check_audio(audio_path: str, transcript: str):
    audio_base64 = audio_file_to_base64(audio_path)

    prompt = f"""
You are reviewing the AUDIO of a short-form edited video.

IMPORTANT CONTEXT:
- This is social-media style edited content
- Sound effects like dings, whooshes, pops, transitions, and emphasis sounds may be intentional
- Do NOT treat sound effects as problems just because they are present
- Only flag sound effects if they clearly overpower speech, feel excessive, or reduce the viewing experience

Your task:
Evaluate:
- voice clarity
- background noise
- whether sound effects/music fit the style
- whether audio supports or hurts the viewing experience

IMPORTANT:
- Be balanced and practical
- Do NOT overreact to common editing effects
- Do NOT list many repetitive timestamps for the same issue
- Only mention 1–3 timestamps for the clearest examples if really needed
- If the voices are clear overall, say so clearly
- If SFX are stylistic and acceptable, acknowledge that

SCORING:
5 = excellent, polished audio
4 = good audio with minor issues
3 = acceptable / average
2 = noticeably distracting
1 = poor

Return EXACT JSON:

{{
  "score": 3,
  "summary": "Short balanced explanation.",
  "strengths": ["point"],
  "issues": ["point"],
  "suggestions": ["point"],
  "timestamp_notes": ["00:59 - example note"]
}}

Transcript:
{transcript[:800]}
"""

    try:
        result = ask_ai_audio(prompt, audio_base64)
        parsed = safe_json_parse(result)

        if parsed:
            return {
                "score": parsed.get("score", 3),
                "summary": parsed.get("summary", "Could not analyze audio reliably."),
                "strengths": parsed.get("strengths", []),
                "issues": parsed.get("issues", []),
                "suggestions": parsed.get("suggestions", []),
                "timestamp_notes": parsed.get("timestamp_notes", [])
            }
    except:
        pass

    # fallback if AI audio review fails
    return fallback_audio_review(audio_path)
   