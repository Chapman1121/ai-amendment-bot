import os
import base64
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

from transcription_service import transcribe_audio_with_openai
from transcript_correction import (
    context_correct_transcript,
    extract_onscreen_text,
    brand_correct_transcript,
    extract_hint_words,
)
from glossary_extractor import extract_glossary
from hook_check import check_hook
from typo_check import check_typos
from grammar_check import check_grammar
from storytelling_check import check_storytelling
from required_elements_check import check_required_elements
from information_clarity_check import check_information_clarity
from review_summary import generate_review_summary
from story_clarity_check import check_story_clarity
from visual_check import check_visuals, extract_frames, extract_subtitle_frames
from audio_check import check_audio, get_ffmpeg_audio_stats


def _audio_quality_warning(audio_path: str):
    try:
        stats = get_ffmpeg_audio_stats(audio_path) or {}
    except Exception:
        return None

    mean_vol = stats.get("mean_volume")
    max_vol = stats.get("max_volume")
    issues = []

    if mean_vol is None and max_vol is None:
        return None

    if mean_vol is not None and mean_vol < -30:
        issues.append(
            f"Audio is very quiet (mean ≈ {mean_vol:.1f} dB). "
            "Transcription accuracy will likely suffer — consider re-recording "
            "with a clip-on / lavalier mic or boosting levels in post."
        )
    if max_vol is not None and max_vol >= -1:
        issues.append(
            f"Audio peaks at {max_vol:.1f} dB — very close to clipping. "
            "Speech may sound distorted, which can confuse the transcriber."
        )
    if mean_vol is not None and mean_vol > -10:
        issues.append(
            f"Audio is unusually loud (mean ≈ {mean_vol:.1f} dB). "
            "Heavy compression may be muddying speech for the transcriber."
        )

    if not issues:
        return None

    severity = "high" if any("clipping" in m or "very quiet" in m for m in issues) else "medium"
    return {"severity": severity, "messages": issues, "stats": stats}


def extract_full_audio(video_path: str) -> str:
    audio_fd, audio_path = tempfile.mkstemp(suffix=".mp3")
    os.close(audio_fd)
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", audio_path]
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


def _safe_call(callable_, *args, default=None, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except Exception:
        return default


def _run_checker(checker, transcript: str, segment_data: list, glossary: list):
    rows = checker(transcript, glossary) or []
    for row in rows:
        row["Timestamp"] = find_timestamp(row.get("Snippet", ""), segment_data)
    return rows


def _run_checker_multimodal(checker, transcript: str, segment_data: list, frames: list, audio_base64: str):
    rows = checker(transcript, frames, audio_base64) or []
    for row in rows:
        row["Timestamp"] = find_timestamp(row.get("Snippet", ""), segment_data)
    return rows


def _checker_failed_row(checker, transcript: str, exc: Exception):
    return {
        "Type": checker.__name__.replace("check_", "").replace("_", " ").title(),
        "Location": "System",
        "Snippet": transcript[:120],
        "Issue": "Checker failed",
        "Suggestion": str(exc)[:250],
        "Severity": "Medium",
        "Timestamp": "N/A",
    }


def _snippets_are_similar(a: str, b: str, threshold: float = 0.7) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    if not a or not b:
        return False
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if short in long:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _dedupe_rows(rows: list):
    severity_order = {"High": 0, "Medium": 1, "Low": 2}
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            severity_order.get(r.get("Severity", "Medium"), 1),
            r.get("Timestamp", "N/A"),
        ),
    )
    deduped: list = []
    for row in rows_sorted:
        row_type = str(row.get("Type", "")).strip().lower()
        row_snippet = str(row.get("Snippet", "")).strip().lower()
        is_dupe = any(
            str(kept.get("Type", "")).strip().lower() == row_type
            and _snippets_are_similar(row_snippet, str(kept.get("Snippet", "")))
            for kept in deduped
        )
        if not is_dupe:
            deduped.append(row)
    return deduped


def _fallback_empty_result(segment_data: list):
    return {
        "transcript": "",
        "segment_data": segment_data,
        "review_flags": [],
        "rows": [{
            "Type": "Video QC", "Location": "Video", "Snippet": "",
            "Issue": "No transcript generated",
            "Suggestion": "Check whether the video has clear spoken audio.",
            "Severity": "High", "Timestamp": "N/A",
        }],
        "info": {"score": 1, "summary": "Could not review information clarity because no transcript was generated.", "strengths": [], "improvements": ["Check audio clarity and transcription input."]},
        "summary": {"story_score": 1, "overall_review": "Could not complete the review because no transcript was generated.", "retention": "Low", "suggestions": ["Check audio quality and try again."]},
        "visual": {"score": 3, "summary": "Could not analyze visuals reliably.", "strengths": [], "issues": [], "suggestions": [], "frame_timestamps": []},
        "audio": {"score": 3, "summary": "Could not analyze audio reliably.", "strengths": [], "issues": [], "suggestions": [], "timestamp_notes": []},
    }


def _default_info():
    return {"score": 3, "summary": "Could not analyze information clarity reliably.", "strengths": [], "improvements": []}

def _default_summary():
    return {"story_score": 3, "overall_review": "Could not generate an overall review reliably.", "retention": "Medium", "suggestions": []}

def _default_story_clarity():
    return {"score": 3, "summary": "Could not analyze story clarity reliably.", "strengths": [], "improvements": []}

def _default_visual(frames: list):
    return {"score": 3, "summary": "Could not analyze visuals reliably.", "strengths": [], "issues": [], "suggestions": [], "frame_timestamps": [f.get("timestamp", "N/A") for f in (frames or [])]}

def _default_audio():
    return {"score": 3, "summary": "Could not analyze audio reliably.", "strengths": [], "issues": [], "suggestions": [], "timestamp_notes": []}


def run_video_qc(video_path: str, progress=None, max_frames: int = 16):
    def _emit(stage, message):
        if progress is None:
            return
        try:
            progress(stage, message)
        except Exception:
            pass

    _emit("audio_extract", "Extracting audio from video...")
    audio_path = extract_full_audio(video_path)
    _emit("audio_extract_done", "Audio extracted")

    audio_warning = _audio_quality_warning(audio_path)
    if audio_warning:
        _emit("audio_warning", f"Audio quality alert ({audio_warning.get('severity', 'medium')})")

    # Pre-transcription: scan frames for key words to pass to Whisper as hints
    _emit("transcribe", "Scanning video for key words...")
    pre_frames = _safe_call(extract_frames, video_path, default=[], max_frames=16) or []
    hint_words = _safe_call(extract_hint_words, pre_frames, default="") or ""
    if hint_words:
        _emit("transcribe", f"Hints found: {hint_words[:80]}")

    try:
        _emit("transcribe", "Transcribing audio with Whisper...")
        raw_transcript, raw_segment_data = transcribe_audio_with_openai(
            audio_path, hint_words=hint_words
        )

        transcript = raw_transcript.strip()
        segment_data = raw_segment_data or []
        review_flags = []

        _emit("transcribe_done", f"Transcript: {len(segment_data)} segments")

        if not transcript:
            _emit("done", "No transcript — returning fallback result")
            return _fallback_empty_result(segment_data)

        _emit("glossary", "Extracting glossary (brands, names)...")
        glossary = _safe_call(extract_glossary, transcript, default=[]) or []
        _emit("glossary_done", f"Glossary: {len(glossary)} term(s)")

        _emit("frames", f"Sampling up to {max_frames} frames across the video...")
        frames = extract_frames(video_path, max_frames=max_frames)
        _emit("frames_done", f"Frames: {len(frames)} sampled")

        # --- TRANSCRIPT CORRECTION ---

        # Step 1: context-aware pass — fixes accent mishearings using GPT context
        _emit("transcript_fix", "Fixing transcript mishearings (context pass)...")
        context_fixed = _safe_call(
            context_correct_transcript, transcript, default=transcript
        ) or transcript
        if context_fixed != transcript:
            _emit("transcript_fix_done", "Context corrections applied")
            transcript = context_fixed
        else:
            _emit("transcript_fix_done", "No context corrections needed")

        # Step 2: extract on-screen caption text for brand name correction
        _emit("transcript_fix", "Reading on-screen captions...")
        subtitle_frames = _safe_call(
            extract_subtitle_frames, video_path, default=[], interval_sec=2.0
        ) or []
        onscreen_text = _safe_call(extract_onscreen_text, subtitle_frames, default="") or ""

        # Step 3: brand name pass — fixes product/brand names using OCR captions
        if onscreen_text:
            brand_fixed = _safe_call(
                brand_correct_transcript, transcript, onscreen_text, default=transcript
            ) or transcript
            if brand_fixed != transcript:
                _emit("transcript_fix_done", "Brand name corrections applied")
                transcript = brand_fixed
            else:
                _emit("transcript_fix_done", "No brand name corrections needed")
        else:
            _emit("transcript_fix_done", "No on-screen captions found — skipping brand pass")

        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode("utf-8")

        rows = []
        _emit("checks", "Running 9 QC checks in parallel...")

        text_checkers = [check_typos, check_grammar]
        multimodal_checkers = [check_hook, check_storytelling, check_required_elements]

        from activity_log import pretty_name as _pretty

        info = _default_info()
        summary = _default_summary()
        story_clarity = _default_story_clarity()
        visual = _default_visual(frames)
        audio = _default_audio()

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {}

            for checker in text_checkers:
                _emit("check_started", _pretty(checker))
                futures[pool.submit(_run_checker, checker, transcript, segment_data, glossary)] = ("checker_text", checker)

            for checker in multimodal_checkers:
                _emit("check_started", _pretty(checker))
                futures[pool.submit(_run_checker_multimodal, checker, transcript, segment_data, frames, audio_base64)] = ("checker_mm", checker)

            _emit("check_started", "Information Clarity")
            futures[pool.submit(check_information_clarity, transcript)] = ("info", None)

            _emit("check_started", "Story Clarity")
            futures[pool.submit(check_story_clarity, transcript)] = ("story_clarity", None)

            _emit("check_started", "Overall Summary")
            futures[pool.submit(generate_review_summary, transcript)] = ("summary", None)

            _emit("check_started", "Visual Review")
            futures[pool.submit(check_visuals, video_path, transcript, frames)] = ("visual", None)

            _emit("check_started", "Audio Review")
            futures[pool.submit(check_audio, audio_path, transcript)] = ("audio", None)

            for fut in as_completed(futures):
                kind, checker = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:
                    if kind in ("checker_text", "checker_mm"):
                        rows.append(_checker_failed_row(checker, transcript, exc))
                        _emit("check_err", f"{_pretty(checker)} failed")
                    elif kind == "info":
                        _emit("check_err", "Information Clarity failed")
                    elif kind == "story_clarity":
                        _emit("check_err", "Story Clarity failed")
                    elif kind == "summary":
                        _emit("check_err", "Overall Summary failed")
                    elif kind == "visual":
                        _emit("check_err", "Visual Review failed")
                    elif kind == "audio":
                        audio["summary"] = f"Could not analyze audio reliably. Error: {str(exc)[:200]}"
                        _emit("check_err", "Audio Review failed")
                    continue

                if kind in ("checker_text", "checker_mm"):
                    rows.extend(res or [])
                    _emit("check_done", f"{_pretty(checker)} done ({len(res or [])} row(s))")
                elif kind == "info":
                    info = res or _default_info()
                    _emit("check_done", f"Information Clarity done ({info.get('score', '-')}/5)")
                elif kind == "story_clarity":
                    story_clarity = res or _default_story_clarity()
                    _emit("check_done", f"Story Clarity done ({story_clarity.get('score', '-')}/5)")
                elif kind == "summary":
                    summary = res or _default_summary()
                    _emit("check_done", "Overall Summary done")
                elif kind == "visual":
                    visual = res or _default_visual(frames)
                    _emit("check_done", f"Visual Review done ({visual.get('score', '-')}/5)")
                elif kind == "audio":
                    audio = res or _default_audio()
                    _emit("check_done", f"Audio Review done ({audio.get('score', '-')}/5)")

        _emit("dedupe", "Consolidating findings...")
        rows = _dedupe_rows(rows)
        _emit("dedupe_done", f"{len(rows)} row(s) after dedupe")

        if not rows:
            rows = [{
                "Type": "QC", "Location": "Transcript", "Snippet": transcript[:120],
                "Issue": "No major issues detected",
                "Suggestion": "Current review looks acceptable.",
                "Severity": "Low", "Timestamp": "N/A",
            }]

        _emit("done", "Analysis complete.")

        return {
            "transcript": transcript,
            "segment_data": segment_data,
            "review_flags": review_flags,
            "rows": rows,
            "info": info,
            "story_clarity": story_clarity,
            "summary": summary,
            "visual": visual,
            "audio": audio,
            "audio_warning": audio_warning,
            "frames": frames,
            "glossary": glossary,
            "audio_base64": audio_base64,
        }

    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


def run_qc_checks_only(
    transcript: str,
    frames: list,
    audio_base64: str,
    segment_data: list,
    video_path: str,
    glossary: list,
    progress=None,
):
    """Re-run QC checks with an edited transcript — skips transcription and frame extraction."""
    def _emit(stage, message):
        if progress is None:
            return
        try:
            progress(stage, message)
        except Exception:
            pass

    rows = []
    _emit("checks", "Re-running QC checks with corrected transcript...")

    text_checkers = [check_typos, check_grammar]
    multimodal_checkers = [check_hook, check_storytelling, check_required_elements]

    from activity_log import pretty_name as _pretty

    info = _default_info()
    summary = _default_summary()
    story_clarity = _default_story_clarity()
    visual = _default_visual(frames)
    audio = _default_audio()

    # Decode audio_base64 back to a temp file so check_audio can read it.
    audio_path = None
    try:
        audio_data = base64.b64decode(audio_base64)
        audio_fd, audio_path = tempfile.mkstemp(suffix=".mp3")
        os.close(audio_fd)
        with open(audio_path, "wb") as f:
            f.write(audio_data)
    except Exception:
        audio_path = None

    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {}

            for checker in text_checkers:
                _emit("check_started", _pretty(checker))
                futures[pool.submit(_run_checker, checker, transcript, segment_data, glossary)] = ("checker_text", checker)

            for checker in multimodal_checkers:
                _emit("check_started", _pretty(checker))
                futures[pool.submit(_run_checker_multimodal, checker, transcript, segment_data, frames, audio_base64)] = ("checker_mm", checker)

            _emit("check_started", "Information Clarity")
            futures[pool.submit(check_information_clarity, transcript)] = ("info", None)

            _emit("check_started", "Story Clarity")
            futures[pool.submit(check_story_clarity, transcript)] = ("story_clarity", None)

            _emit("check_started", "Overall Summary")
            futures[pool.submit(generate_review_summary, transcript)] = ("summary", None)

            _emit("check_started", "Visual Review")
            futures[pool.submit(check_visuals, video_path, transcript, frames)] = ("visual", None)

            if audio_path:
                _emit("check_started", "Audio Review")
                futures[pool.submit(check_audio, audio_path, transcript)] = ("audio", None)

            for fut in as_completed(futures):
                kind, checker = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:
                    if kind in ("checker_text", "checker_mm"):
                        rows.append(_checker_failed_row(checker, transcript, exc))
                        _emit("check_err", f"{_pretty(checker)} failed")
                    elif kind == "info":
                        _emit("check_err", "Information Clarity failed")
                    elif kind == "story_clarity":
                        _emit("check_err", "Story Clarity failed")
                    elif kind == "summary":
                        _emit("check_err", "Overall Summary failed")
                    elif kind == "visual":
                        _emit("check_err", "Visual Review failed")
                    elif kind == "audio":
                        audio["summary"] = f"Could not analyze audio reliably. Error: {str(exc)[:200]}"
                        _emit("check_err", "Audio Review failed")
                    continue

                if kind in ("checker_text", "checker_mm"):
                    rows.extend(res or [])
                    _emit("check_done", f"{_pretty(checker)} done ({len(res or [])} row(s))")
                elif kind == "info":
                    info = res or _default_info()
                    _emit("check_done", f"Information Clarity done ({info.get('score', '-')}/5)")
                elif kind == "story_clarity":
                    story_clarity = res or _default_story_clarity()
                    _emit("check_done", f"Story Clarity done ({story_clarity.get('score', '-')}/5)")
                elif kind == "summary":
                    summary = res or _default_summary()
                    _emit("check_done", "Overall Summary done")
                elif kind == "visual":
                    visual = res or _default_visual(frames)
                    _emit("check_done", f"Visual Review done ({visual.get('score', '-')}/5)")
                elif kind == "audio":
                    audio = res or _default_audio()
                    _emit("check_done", f"Audio Review done ({audio.get('score', '-')}/5)")

    finally:
        if audio_path:
            try:
                os.remove(audio_path)
            except OSError:
                pass

    _emit("dedupe", "Consolidating findings...")
    rows = _dedupe_rows(rows)
    _emit("dedupe_done", f"{len(rows)} row(s) after dedupe")

    if not rows:
        rows = [{
            "Type": "QC", "Location": "Transcript", "Snippet": transcript[:120],
            "Issue": "No major issues detected",
            "Suggestion": "Current review looks acceptable.",
            "Severity": "Low", "Timestamp": "N/A",
        }]

    _emit("done", "Re-analysis complete.")

    return {
        "rows": rows,
        "info": info,
        "story_clarity": story_clarity,
        "summary": summary,
        "visual": visual,
        "audio": audio,
    }
