import json
from connection import transcribe_audio_file


def _seconds_to_mmss(value) -> str:
    try:
        total = int(float(value))
    except Exception:
        return "N/A"

    mm = total // 60
    ss = total % 60
    return f"{mm:02d}:{ss:02d}"


def _extract_json_block(text: str) -> dict:
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1

    if start == -1 or end == 0:
        raise Exception(f"Could not parse transcript JSON: {text[:600]}")

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise Exception(f"Invalid transcript JSON: {text[:600]}") from exc


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
        # Fallback: bucket words into ~5 second chunks if only word timings exist.
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
        transcript = " ".join(seg["text"] for seg in segment_data if seg["text"]).strip()

    if not transcript:
        raise Exception("Transcript was empty after parsing OpenAI response.")

    return transcript, segment_data


# Backward-compatible alias so older imports still work.
def transcribe_audio_with_gemini(audio_path: str):
    return transcribe_audio_with_openai(audio_path)
