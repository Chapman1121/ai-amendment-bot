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


def _legacy_extract_frames(video_path: str, num_frames: int = 4):
    """Original fixed-percentage extraction kept as a safety-net fallback."""
    duration = get_video_duration(video_path)
    temp_dir = tempfile.mkdtemp(prefix="frames_legacy_")
    ratios = [0.10, 0.35, 0.60, 0.93][:num_frames]
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
            out_path,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(out_path):
            frames.append({
                "timestamp": seconds_to_mmss(ts),
                "base64": file_to_base64(out_path),
            })

    return frames


def extract_frames(
    video_path: str,
    num_frames: int = None,
    max_frames: int = 16,
    scene_threshold: float = 0.30,
    min_interval_sec: float = 2.0,
):
    """
    Sample frames covering the ENTIRE video, with scene-change awareness.

    Strategy:
      1. ffmpeg's scene-change detector picks frames where the visual content
         changes significantly (CTAs, b-roll inserts, cuts, end cards).
      2. Interval sampling guarantees coverage of static stretches — the
         interval scales with duration so a 5-minute video doesn't blow up
         the frame count.
      3. The result is capped at `max_frames` to keep API cost predictable.

    Backward-compatible: callers passing `num_frames=4` still work; `num_frames`
    is treated as a soft floor on the cap.
    """
    if num_frames is not None:
        max_frames = max(int(num_frames), max_frames)

    duration = get_video_duration(video_path)
    temp_dir = tempfile.mkdtemp(prefix="frames_")

    # Scale interval so very long videos don't generate hundreds of frames.
    # e.g. 60s video / 16 frames = ~4s interval (clamped to min_interval_sec).
    target_interval = max(min_interval_sec, duration / max(max_frames, 1))

    # Combined ffmpeg select filter — pick a frame if ANY of these are true:
    #   gt(scene, T)                  -> significant visual change
    #   isnan(prev_selected_t)        -> first frame (always include opener)
    #   gte(t - prev_selected_t, I)   -> at least I seconds since last keep
    select_expr = (
        f"select='gt(scene\\,{scene_threshold})"
        f"+isnan(prev_selected_t)"
        f"+gte(t-prev_selected_t\\,{target_interval})',"
        f"showinfo"
    )

    out_pattern = os.path.join(temp_dir, "frame_%04d.jpg")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", select_expr,
        "-vsync", "vfr",
        "-q:v", "4",
        out_pattern,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
        )
    except Exception:
        # If the combined filter fails for any reason, fall back to legacy.
        return _legacy_extract_frames(video_path, num_frames=4)

    # Parse showinfo lines on stderr for the pts_time of each selected frame.
    timestamps = []
    for line in (result.stderr or "").splitlines():
        if "pts_time:" in line:
            try:
                t_str = line.split("pts_time:")[1].split()[0]
                timestamps.append(float(t_str))
            except (ValueError, IndexError):
                pass

    files = sorted(
        f for f in os.listdir(temp_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )

    # Belt-and-braces cap: if scene detection produced more than max_frames,
    # evenly downsample so we keep coverage of the full timeline.
    if len(files) > max_frames:
        n = max_frames
        idxs = [int(round(i * (len(files) - 1) / max(n - 1, 1))) for i in range(n)]
        # de-dupe while preserving order
        seen, ordered = set(), []
        for i in idxs:
            if i not in seen:
                ordered.append(i)
                seen.add(i)
        files = [files[i] for i in ordered]
        if len(timestamps) >= max(ordered) + 1:
            timestamps = [timestamps[i] for i in ordered]

    frames = []
    for i, fname in enumerate(files):
        path = os.path.join(temp_dir, fname)
        ts = timestamps[i] if i < len(timestamps) else 0.0
        if not os.path.exists(path):
            continue
        frames.append({
            "timestamp": seconds_to_mmss(ts),
            "base64": file_to_base64(path),
        })

    # Last-resort fallback: if scene detection somehow produced nothing,
    # fall back to the original four-percentage sampler.
    if not frames:
        frames = _legacy_extract_frames(video_path, num_frames=4)

    return frames


def extract_subtitle_frames(video_path: str, interval_sec: float = 2.0) -> list:
    """
    Extract one frame every `interval_sec` seconds across the entire video.
    Designed for dense subtitle/caption OCR — guarantees every subtitle
    visible on screen is captured regardless of scene changes.

    Returns a list of dicts: [{"timestamp": "MM:SS", "base64": "..."}]
    """
    duration = get_video_duration(video_path)
    temp_dir = tempfile.mkdtemp(prefix="subtitle_frames_")

    # Use ffmpeg fps filter: 1 frame every interval_sec seconds
    fps = 1.0 / max(interval_sec, 0.5)
    out_pattern = os.path.join(temp_dir, "frame_%04d.jpg")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "5",   # slightly lower quality to keep file sizes small
        out_pattern,
    ]

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except Exception:
        return []

    files = sorted(
        f for f in os.listdir(temp_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )

    frames = []
    for i, fname in enumerate(files):
        path = os.path.join(temp_dir, fname)
        if not os.path.exists(path):
            continue
        ts = i * interval_sec
        frames.append({
            "timestamp": seconds_to_mmss(ts),
            "base64": file_to_base64(path),
        })

    return frames


def check_visuals(video_path: str, transcript: str, frames: list | None = None):
    # Reuse pre-extracted frames if provided to avoid running ffmpeg twice.
    if not frames:
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

    frames_index = "\n".join(
        f"- Frame {i+1}: t={f.get('timestamp', 'N/A')}"
        for i, f in enumerate(frames)
    )

    prompt = f"""
You are reviewing the VISUAL quality of a short-form edited video.

OUTPUT RULES:
- ALWAYS return valid JSON
- NEVER return empty output
- NEVER include text outside JSON
- Be realistic, balanced, and practical

GROUNDING RULES (READ THIS FIRST):
- Base every observation ONLY on what is actually visible in the frames provided.
- Do NOT speculate about what might happen between frames you cannot see.
- Do NOT invent products, characters, locations, or events that are not visibly present.
- If you are unsure whether something is on screen, do NOT mention it.
- Reference frame timestamps when you describe visual evidence.

FRAME COVERAGE:
- The frames below are sampled across the ENTIRE video (scene-change aware
  + interval sampling), so opening / middle / end CTAs, b-roll, end-cards
  and graphics overlays are all in scope.
- When you flag something, cite the timestamp (e.g. "CTA visible at 01:23").

Frame index (in order shown):
{frames_index}

CHANNEL STYLE — VERY IMPORTANT, DO NOT VIOLATE:
- This is a short-form channel where SINGLE-LOCATION talking-head shots are
  the intentional and expected style.
- ❌ DO NOT flag "plain background", "static location", "same setting",
  "repetitive scenery", or "lack of visual variety" as issues. These are
  stylistic choices, NOT problems.
- ❌ DO NOT lower the score because the location does not change.
- ✅ DO judge framing quality, lighting, subject clarity, and on-screen graphics.
- ✅ A well-framed single-location video can score 4 or 5.

CTA / GRAPHICS HUNT (do this carefully):
- Look beyond the persistent channel watermark. The watermark alone is NOT a CTA.
- Specifically scan every frame for:
   * small text overlays (e.g. "Follow for more", "Swipe up", "@handle")
   * mid-video CTA cards or pinned graphics
   * end-cards or closing graphics in the final frames
   * follow / subscribe buttons or arrows
   * product or brand callouts
- A small CTA in one or two frames still counts — flag its timestamp.
- Distinguish "watermark only" from "real CTA present"; the difference matters.

Evaluate:
- framing and subject clarity
- lighting quality
- whether the speaker is well-positioned and easy to watch
- whether on-screen text, graphics, or CTAs are visible and clear
- whether the opening frame is engaging enough to stop a viewer from scrolling
- whether any mid-video or end-card CTA / branding graphic is present and readable

SCORING:
5 = very strong — excellent framing, lighting, and clear on-screen graphics
4 = good — clean framing and lighting, CTA or branding visible
3 = acceptable — serviceable visuals, nothing distracting
2 = weak — poor framing, bad lighting, or CTA is missing/unclear
1 = very poor — visuals actively hurt the viewing experience

IMPORTANT:
- Do NOT drop the score just because the background is the same across frames
- A well-framed single-location video can still score 4
- Only give 5 if framing, lighting, and graphics are all strong

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
