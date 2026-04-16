import os
import base64
import subprocess
import tempfile
from difflib import SequenceMatcher

from transcription_service import transcribe_audio_with_openai
from hook_check import check_hook
from typo_check import check_typos
from grammar_check import check_grammar
from storytelling_check import check_storytelling
from required_elements_check import check_required_elements
from information_clarity_check import check_information_clarity
from review_summary import generate_review_summary
from visual_check import check_visuals, extract_frames
from audio_check import check_audio


def extract_full_audio(video_path: str) -> str:
    audio_fd, audio_path = tempfile.mkstemp(suffix=".mp3")
    os.close(audio_fd)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "libmp3lame",
        audio_path,
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return audio_path


def find_timestamp(snippet: str, segment_data: list):
    snippet = (snippet or "").lower().strip()
    if not snippet or not segment_data:
        return "N/A"

    best_score = 0.0
    best_time = "N/A"

    for seg in segment_data:
        if not isinstance(seg, dict):
            continue

        seg_text = str(seg.get("text", "")).lower().strip()
        if not seg_text:
            continue

        if snippet in seg_text or seg_text in snippet:
            return seg.get("start", "N/A")

        score = SequenceMatcher(None, snippet, seg_text).ratio()
        if score > best_score:
            best_score = score
            best_time = seg.get("start", "N/A")

    return best_time if best_score >= 0.35 else "N/A"


def _run_checker(checker, transcript: str, segment_data: list):
    rows = checker(transcript)
    for row in rows:
        row["Timestamp"] = find_timestamp(row.get("Snippet", ""), segment_data)
    return rows


def _run_checker_multimodal(
    checker,
    transcript: str,
    segment_data: list,
    frames: list,
    audio_base64: str,
):
    rows = checker(transcript, frames, audio_base64)
    for row in rows:
        row["Timestamp"] = find_timestamp(row.get("Snippet", ""), segment_data)
    return rows


def _dedupe_rows(rows: list):
    deduped = []
    seen = set()

    for row in rows:
        key = (
            str(row.get("Type", "")).strip().lower(),
            str(row.get("Snippet", "")).strip().lower(),
            str(row.get("Issue", "")).strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    severity_order = {"High": 0, "Medium": 1, "Low": 2}
    deduped.sort(
        key=lambda r: (
            severity_order.get(r.get("Severity", "Medium"), 1),
            r.get("Timestamp", "N/A"),
        )
    )
    return deduped


def _fallback_empty_result(segment_data: list):
    return {
        "transcript": "",
        "segment_data": segment_data,
        "review_flags": [],
        "rows": [{
            "Type": "Video QC",
            "Location": "Video",
            "Snippet": "",
            "Issue": "No transcript generated",
            "Suggestion": "Check whether the video has clear spoken audio.",
            "Severity": "High",
            "Timestamp": "N/A",
        }],
        "info": {
            "score": 1,
            "summary": "Could not review information clarity because no transcript was generated.",
            "strengths": [],
            "improvements": ["Check audio clarity and transcription input."],
        },
        "summary": {
            "story_score": 1,
            "overall_review": "Could not complete the review because no transcript was generated.",
            "retention": "Low",
            "suggestions": ["Check audio quality and try again."],
        },
        "visual": {
            "score": 3,
            "summary": "Could not analyze visuals reliably.",
            "strengths": [],
            "issues": [],
            "suggestions": [],
            "frame_timestamps": [],
        },
        "audio": {
            "score": 3,
            "summary": "Could not analyze audio reliably.",
            "strengths": [],
            "issues": [],
            "suggestions": [],
            "timestamp_notes": [],
        },
    }


def run_video_qc(video_path: str):
    audio_path = extract_full_audio(video_path)

    try:
        raw_transcript, raw_segment_data = transcribe_audio_with_openai(audio_path)

        transcript = raw_transcript.strip()
        segment_data = raw_segment_data or []
        review_flags = []

        if not transcript:
            return _fallback_empty_result(segment_data)

        frames = extract_frames(video_path, num_frames=4)

        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode("utf-8")

        rows = []

        # Transcript-based checks
        for checker in [check_typos, check_grammar]:
            try:
                rows.extend(_run_checker(checker, transcript, segment_data))
            except Exception as exc:
                rows.append({
                    "Type": checker.__name__.replace("check_", "").replace("_", " ").title(),
                    "Location": "System",
                    "Snippet": transcript[:120],
                    "Issue": "Checker failed",
                    "Suggestion": str(exc)[:250],
                    "Severity": "Medium",
                    "Timestamp": "N/A",
                })

        # Multimodal QC Board rows: always assessment row + optional issue rows
        for checker in [check_hook, check_storytelling, check_required_elements]:
            try:
                rows.extend(
                    _run_checker_multimodal(
                        checker,
                        transcript,
                        segment_data,
                        frames,
                        audio_base64,
                    )
                )
            except Exception as exc:
                rows.append({
                    "Type": checker.__name__.replace("check_", "").replace("_", " ").title(),
                    "Location": "System",
                    "Snippet": transcript[:120],
                    "Issue": "Checker failed",
                    "Suggestion": str(exc)[:250],
                    "Severity": "Medium",
                    "Timestamp": "N/A",
                })

        rows = _dedupe_rows(rows)

        if not rows:
            rows = [{
                "Type": "QC",
                "Location": "Transcript",
                "Snippet": transcript[:120],
                "Issue": "No major issues detected",
                "Suggestion": "Current review looks acceptable.",
                "Severity": "Low",
                "Timestamp": "N/A",
            }]

        try:
            info = check_information_clarity(transcript) or {
                "score": 3,
                "summary": "Could not analyze information clarity reliably.",
                "strengths": [],
                "improvements": [],
            }
        except Exception:
            info = {
                "score": 3,
                "summary": "Could not analyze information clarity reliably.",
                "strengths": [],
                "improvements": [],
            }

        try:
            summary = generate_review_summary(transcript) or {
                "story_score": 3,
                "overall_review": "Could not generate an overall review reliably.",
                "retention": "Medium",
                "suggestions": [],
            }
        except Exception:
            summary = {
                "story_score": 3,
                "overall_review": "Could not generate an overall review reliably.",
                "retention": "Medium",
                "suggestions": [],
            }

        try:
            visual = check_visuals(video_path, transcript) or {
                "score": 3,
                "summary": "Could not analyze visuals reliably.",
                "strengths": [],
                "issues": [],
                "suggestions": [],
                "frame_timestamps": [],
            }
        except Exception:
            visual = {
                "score": 3,
                "summary": "Could not analyze visuals reliably.",
                "strengths": [],
                "issues": [],
                "suggestions": [],
                "frame_timestamps": [],
            }

        try:
            audio = check_audio(audio_path, transcript) or {
                "score": 3,
                "summary": "Could not analyze audio reliably.",
                "strengths": [],
                "issues": [],
                "suggestions": [],
                "timestamp_notes": [],
            }
        except Exception as exc:
            audio = {
                "score": 3,
                "summary": f"Could not analyze audio reliably. Error: {str(exc)[:200]}",
                "strengths": [],
                "issues": [],
                "suggestions": [],
                "timestamp_notes": [],
            }

        return {
            "transcript": transcript,
            "segment_data": segment_data,
            "review_flags": review_flags,
            "rows": rows,
            "info": info,
            "summary": summary,
            "visual": visual,
            "audio": audio,
        }

    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass