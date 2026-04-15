import base64
import json
import os
import subprocess
import tempfile

from connection import ask_ai_images


def get_video_duration(video_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except:
        return 60.0


def seconds_to_mmss(seconds: float) -> str:
    total = int(seconds)
    mm = total // 60
    ss = total % 60
    return f"{mm:02d}:{ss:02d}"


def file_to_base64(path: str) -> str:
    with open(path, "rb") as f:
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


def extract_frames(video_path: str, num_frames=4):
    duration = get_video_duration(video_path)
    temp_dir = tempfile.mkdtemp(prefix="frames_")

    # lighter and safer than 6
    ratios = [0.10, 0.35, 0.60, 0.85][:num_frames]

    frames = []

    for i, ratio in enumerate(ratios, start=1):
        ts = duration * ratio
        out_path = os.path.join(temp_dir, f"frame_{i:02d}.jpg")

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(ts),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "4",
            out_path
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(out_path):
            frames.append({
                "timestamp": seconds_to_mmss(ts),
                "base64": file_to_base64(out_path)
            })

    return frames


def check_visuals(video_path: str, transcript: str):
    frames = extract_frames(video_path, num_frames=4)

    if not frames:
        return {
            "score": 3,
            "summary": "Could not analyze visuals reliably because no frames were extracted.",
            "strengths": [],
            "issues": [],
            "suggestions": [],
            "frame_timestamps": []
        }

    prompt = f"""
You are reviewing the VISUAL quality of a short-form edited video.

IMPORTANT:
- ALWAYS return valid JSON
- NEVER return empty output
- NEVER include text outside JSON
- Be realistic, balanced, and practical

Evaluate:
- visual variety
- framing clarity
- whether visuals support what is being said
- whether the opening is visually engaging
- whether visuals help retention

SCORING:
5 = very strong visual storytelling
4 = good visuals with helpful variety
3 = acceptable/basic visuals
2 = weak or repetitive visuals
1 = very poor visuals

IMPORTANT:
- Most interview/talking-style videos = 3
- Only give 4 if visuals actively improve the experience
- Only give 5 if visuals are exceptionally strong

Return EXACT JSON:

{{
  "score": 3,
  "summary": "Short balanced explanation.",
  "strengths": ["point", "point"],
  "issues": ["point", "point"],
  "suggestions": ["point", "point", "point"]
}}

Transcript context:
{transcript[:800]}
"""

    try:
        result = ask_ai_images(prompt, [f["base64"] for f in frames])
        parsed = safe_json_parse(result)

        if parsed:
            return {
                "score": parsed.get("score", 3),
                "summary": parsed.get("summary", "Could not analyze visuals reliably."),
                "strengths": parsed.get("strengths", []),
                "issues": parsed.get("issues", []),
                "suggestions": parsed.get("suggestions", []),
                "frame_timestamps": [f["timestamp"] for f in frames]
            }
    except Exception as e:
        return {
            "score": 3,
            "summary": f"Could not analyze visuals reliably. Error: {str(e)[:200]}",
            "strengths": [],
            "issues": [],
            "suggestions": [],
            "frame_timestamps": [f["timestamp"] for f in frames]
        }

    return {
        "score": 3,
        "summary": "Could not analyze visuals reliably.",
        "strengths": [],
        "issues": [],
        "suggestions": [],
        "frame_timestamps": [f["timestamp"] for f in frames]
    }