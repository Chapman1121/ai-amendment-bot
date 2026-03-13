
import os
import subprocess
import tempfile

from transcription_service import transcribe_audio_with_gemini
from hook_check import check_hook
from typo_check import check_typos
from grammar_check import check_grammar
from storytelling_check import check_storytelling
from required_elements_check import check_required_elements


def extract_full_audio(video_path: str) -> str:
    audio_fd, audio_path = tempfile.mkstemp(suffix=".mp3")
    os.close(audio_fd)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "libmp3lame",
        audio_path
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return audio_path


def transcribe_video(video_path: str) -> str:
    audio_path = extract_full_audio(video_path)
    transcript, segment_data = transcribe_audio_with_gemini(audio_path)
    return transcript, segment_data

    


def find_timestamp(snippet: str, segment_data:
list):
    snippet = snippet.lower().strip()

    if not snippet:
        return "N/A"

    for seg in segment_data:
        seg_text = seg.get("text","").lower().strip()
        if snippet in seg_text or seg_text in snippet:
         return seg.get("start", "N/A")
   
    return "N/A"



def run_video_qc(video_path: str):
 
    transcript, segment_data = transcribe_video(video_path)

    print("FULL TRANSCRIPT:")
    print(transcript)

    if not transcript.strip():
        return [{
            "Type": "Video QC",
            "Location": "Video",
            "Snippet": "",
            "Issue": "No transcript generated",
            "Suggestion": "Check whether the video has clear spoken audio.",
            "Severity": "High"
        }]

    rows = []

    hook_rows = check_hook(transcript)
    for r in hook_rows:
        r["Timestamp"] = find_timestamp(r["Snippet"], segment_data)
    rows.extend(hook_rows)

    typo_rows = check_typos(transcript)
    for r in typo_rows:
        r["Timestamp"] = find_timestamp(r["Snippet"], segment_data)
    rows.extend(typo_rows)

    grammar_rows = check_grammar(transcript)
    for r in grammar_rows:
        r["Timestamp"] = find_timestamp(r["Snippet"], segment_data)
    rows.extend(grammar_rows)

    story_rows = check_storytelling(transcript)
    for r in story_rows:
        r["Timestamp"] = find_timestamp(r["Snippet"], segment_data)
    rows.extend(story_rows)

    element_rows = check_required_elements(transcript)
    for r in element_rows:
        r["Timestamp"] = find_timestamp(r["Snippet"], segment_data)
    rows.extend(element_rows)


    if not rows:
        rows = [{
            "Type": "Hook",
            "Location": "Opening",
            "Snippet": transcript[:120],
            "Issue": "No hook issue detected",
            "Suggestion": "Opening appears acceptable based on current hook analysis.",
            "Severity": "Low"
        }]

    return rows