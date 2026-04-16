import json
from typing import List, Optional

from connection import transcribe_audio_file, ask_ai


def _seconds_to_mmss(value) -> str:
    try:
        total = int(float(value))
    except Exception:
        return "N/A"

    mm = total // 60
    ss = total % 60
    return f"{mm:02d}:{ss:02d}"


def _extract_json_object(text: str) -> Optional[dict]:
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1

    if start == -1 or end == 0:
        return None

    try:
        return json.loads(text[start:end])
    except Exception:
        return None


def transcribe_audio_with_openai(audio_path: str):
    parsed = transcribe_audio_file(audio_path)

    transcript = str(parsed.get("text", "")).strip()
    raw_segments = parsed.get("segments", []) or []
    raw_words = parsed.get("words", []) or []
    segment_data = []

    if isinstance(raw_segments, list) and raw_segments:
        for seg in raw_segments:
            if not isinstance(seg, dict):
                continue

            segment_data.append(
                {
                    "start": _seconds_to_mmss(seg.get("start")),
                    "end": _seconds_to_mmss(seg.get("end")),
                    "text": str(seg.get("text", "")).strip(),
                }
            )

    elif isinstance(raw_words, list) and raw_words:
        bucket = []
        bucket_start = None
        last_end = None

        for word in raw_words:
            if not isinstance(word, dict):
                continue

            start = word.get("start")
            end = word.get("end")
            text = str(word.get("word", "")).strip()

            if start is None or end is None or not text:
                continue

            if bucket_start is None:
                bucket_start = float(start)

            if bucket and float(end) - float(bucket_start) > 5.0:
                segment_data.append(
                    {
                        "start": _seconds_to_mmss(bucket_start),
                        "end": _seconds_to_mmss(last_end),
                        "text": " ".join(bucket).strip(),
                    }
                )
                bucket = []
                bucket_start = float(start)

            bucket.append(text)
            last_end = float(end)

        if bucket:
            segment_data.append(
                {
                    "start": _seconds_to_mmss(bucket_start),
                    "end": _seconds_to_mmss(last_end),
                    "text": " ".join(bucket).strip(),
                }
            )

    if not transcript and segment_data:
        transcript = " ".join(
            seg["text"] for seg in segment_data if isinstance(seg, dict) and seg.get("text")
        ).strip()

    if not transcript:
        raise Exception("Transcript was empty after parsing OpenAI response.")

    return transcript, segment_data

def refine_segment_with_ai(
    segment_text: str,
    prev_text: str = "",
    next_text: str = "",
    glossary: list[str] | None = None,
) -> dict:
    glossary_text = ", ".join(glossary or [])

    prompt = f"""
You are correcting ONE transcript segment from a video.

PRIMARY GOAL:
Maximize transcript accuracy, not readability.

STRICT RULES:
- Stay as close as possible to the original segment.
- Fix ONLY clearly misheard words or broken phrases.
- DO NOT rewrite for style, tone, or fluency.
- DO NOT add new descriptive words.
- DO NOT upgrade vague words into more specific ones.
- DO NOT change meaning unless the original clearly makes no sense.
- If unsure, keep the original wording.

CONTEXT USAGE:
- Use previous and next segments only to resolve unclear words.
- Do NOT invent meaning beyond what is supported.

NAMES / TERMS:
- Preserve names, brands, and repeated words.
- If a word resembles a known term, prefer that.

LOGIC CHECK:
- If a phrase is grammatically fine but semantically illogical, fix it minimally.
- If multiple interpretations exist, choose the most neutral one.

UNCERTAINTY RULE:
- If confidence is low, DO NOT aggressively change the text.
- Instead, keep it similar and mark needs_review = true.

Known likely terms:
{glossary_text}

Previous:
{prev_text}

Current:
{segment_text}

Next:
{next_text}

Return ONLY valid JSON:
{{
  "corrected_text": "text",
  "confidence": 1,
  "needs_review": false,
  "reason": "short reason"
}}

Confidence scale:
1 = very uncertain (likely wrong)
2 = uncertain
3 = moderate confidence
4 = high confidence
5 = very high confidence
"""
    result = ask_ai(prompt).strip()

    try:
        start = result.find("{")
        end = result.rfind("}") + 1
        data = json.loads(result[start:end])

        corrected = str(data.get("corrected_text", segment_text)).strip()
        if not corrected:
            corrected = segment_text

        confidence = int(data.get("confidence", 3))
        confidence = max(1, min(5, confidence))

        needs_review = bool(data.get("needs_review", False))
        reason = str(data.get("reason", "")).strip()

        return {
            "corrected_text": corrected,
            "confidence": confidence,
            "needs_review": needs_review,
            "reason": reason,
        }

    except Exception:
        return {
            "corrected_text": segment_text,
            "confidence": 2,
            "needs_review": True,
            "reason": "Failed to parse AI output",
        }



def refine_segments_with_ai(segment_data: list, glossary: Optional[List[str]] = None):
    corrected_segments = []

    for i, seg in enumerate(segment_data):
        if not isinstance(seg, dict):
            continue

        prev_text = ""
        next_text = ""

        if i > 0 and isinstance(segment_data[i - 1], dict):
            prev_text = str(segment_data[i - 1].get("text", "")).strip()

        if i + 1 < len(segment_data) and isinstance(segment_data[i + 1], dict):
            next_text = str(segment_data[i + 1].get("text", "")).strip()

        curr_text = str(seg.get("text", "")).strip()
        refined = refine_segment_with_ai(curr_text, prev_text, next_text, glossary)

        corrected_segments.append(
            {
                "start": seg.get("start", "N/A"),
                "end": seg.get("end", "N/A"),
                "text": refined["corrected_text"],
                "raw_text": curr_text,
                "confidence": refined["confidence"],
                "needs_review": refined["needs_review"],
                "review_reason": refined["reason"],
            }
        )

    return corrected_segments


def rebuild_transcript_from_segments(segment_data: list) -> str:
    return " ".join(
        str(seg.get("text", "")).strip()
        for seg in segment_data
        if isinstance(seg, dict) and seg.get("text")
    ).strip()


def summarize_transcript_review_flags(segment_data: list):
    flagged = []
    for seg in segment_data:
        if not isinstance(seg, dict):
            continue
        if seg.get("needs_review") or int(seg.get("confidence", 3)) <= 2:
            flagged.append(
                {
                    "start": seg.get("start", "N/A"),
                    "text": seg.get("text", ""),
                    "raw_text": seg.get("raw_text", ""),
                    "confidence": seg.get("confidence", 3),
                    "reason": seg.get("review_reason", ""),
                }
            )
    return flagged


# Backward-compatible wrappers so the rest of your app does not break
def refine_transcript_with_ai(transcript: str) -> str:
    prompt = f"""
You are correcting an AI-generated transcript from a video.

IMPORTANT:
- Fix only clearly misheard words, broken phrases, and obvious transcript errors.
- Keep the natural spoken tone.
- Do not over-formalize.
- Do not rewrite the speaker's personality.
- Preserve names, brands, slang, and casual speech if they appear intentional.
- Use the context of the full conversation to resolve unclear words or phrases.
- If a word or phrase sounds unnatural, illogical, or does not make sense, replace it with the most likely intended meaning.
- Do NOT guess randomly.
- Prefer natural conversational wording based on surrounding lines.
- If the original wording already makes sense, keep it.
- Return ONLY the corrected transcript text.

Transcript:
{transcript}
"""
    result = ask_ai(prompt).strip()
    return result if result else transcript


def verify_transcript_with_audio(transcript: str, segment_data: list) -> str:
    segment_text = "\n".join(
        f"{seg.get('start', 'N/A')} - {seg.get('text', '').strip()}"
        for seg in segment_data[:80]
        if isinstance(seg, dict) and seg.get("text")
    )

    prompt = f"""
You are doing a second-pass transcript verification for a video.

You only have:
1. the full transcript
2. timestamped transcript segments

TASK:
- Fix only obvious mistakes, contradictions, or broken phrases
- Use both the transcript and segment context to resolve unclear wording
- If a phrase does not make logical sense, replace it with the most likely intended meaning
- Keep the original spoken style
- Do not over-rewrite
- Do NOT guess randomly
- Return ONLY the final corrected transcript

Full transcript:
{transcript}

Timestamped segments:
{segment_text}
"""
    result = ask_ai(prompt).strip()
    return result if result else transcript


def transcribe_audio_with_gemini(audio_path: str):
    return transcribe_audio_with_openai(audio_path)