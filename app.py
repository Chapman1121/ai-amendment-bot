import tempfile
import pandas as pd
import streamlit as st

from export_utils import build_report_docx_bytes
from video_qc import run_video_qc


st.set_page_config(page_title="AI Amendment Bot — QC Board", layout="wide")

st.markdown("### Koocester")
st.title("AI Amendment Bot — QC Board")
st.caption("Upload a video → review clarity, summary, visuals, audio, and QC issues.")

uploaded = st.file_uploader("Upload video", type=["mp4", "mov", "mkv", "mpeg4"])


def color_severity(val):
    if val == "High":
        return "background-color: #ff4b4b; color: white;"
    if val == "Medium":
        return "background-color: #ffa500; color: black;"
    if val == "Low":
        return "background-color: #4caf50; color: white;"
    return ""


if uploaded:
    suffix = "." + uploaded.name.split(".")[-1] if "." in uploaded.name else ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getbuffer())
        video_path = tmp.name

    if st.button("Analyze Video"):
        with st.spinner("Transcribing and analyzing video..."):
            result = run_video_qc(video_path)
            docx_bytes = build_report_docx_bytes(result)

        summary = result.get("summary") or {}
        info = result.get("info") or {}
        visual = result.get("visual") or {}
        audio = result.get("audio") or {}
        rows = result.get("rows") or []
        transcript = result.get("transcript") or ""

        st.download_button(
            "Download DOCX Report",
            data=docx_bytes,
            file_name="ai_qc_report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        st.success("Analysis complete")

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Story Clarity", f"{summary.get('story_score', 3)}/5")
        col2.metric("Info Clarity", f"{info.get('score', 3)}/5")
        col3.metric("Visuals", f"{visual.get('score', 3)}/5")
        col4.metric("Audio", f"{audio.get('score', 3)}/5")
        col5.metric("Predicted Retention", summary.get("retention", "Medium"))

        st.subheader("Overall Review")
        st.write(summary.get("overall_review", "No overall review generated."))

        suggestions = summary.get("suggestions", [])
        if suggestions:
            st.subheader("Top Suggestions")
            for item in suggestions:
                st.write(f"- {item}")

        # QC BOARD MOVED OUTSIDE TRANSCRIPT EXPANDER
        st.subheader("QC Board")
        if rows:
            df = pd.DataFrame(rows)

            preferred_order = [
                "Timestamp",
                "Type",
                "Location",
                "Snippet",
                "Issue",
                "Suggestion",
                "Severity",
            ]
            df = df[[c for c in preferred_order if c in df.columns]]

            styled_df = df.style.map(color_severity, subset=["Severity"] if "Severity" in df.columns else [])
            st.dataframe(styled_df, use_container_width=True, height=520)

            st.download_button(
                "Download Report (CSV)",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="video_qc_report.csv",
                mime="text/csv",
            )
        else:
            st.info("No QC rows returned.")

        left, right = st.columns(2)

        with left:
            st.subheader("Information Clarity")
            st.write(info.get("summary", "No information clarity summary generated."))

            strengths = info.get("strengths", [])
            improvements = info.get("improvements", [])

            if strengths:
                st.write("**Strengths**")
                for item in strengths:
                    st.write(f"- {item}")

            if improvements:
                st.write("**Suggested Improvements**")
                for item in improvements:
                    st.write(f"- {item}")

        with right:
            st.subheader("Visual Review")
            st.write(visual.get("summary", "No visual review generated."))

            if visual.get("strengths"):
                st.write("**Strengths**")
                for item in visual["strengths"]:
                    st.write(f"- {item}")

            if visual.get("issues"):
                st.write("**Issues**")
                for item in visual["issues"]:
                    st.write(f"- {item}")

            if visual.get("suggestions"):
                st.write("**Suggestions**")
                for item in visual["suggestions"]:
                    st.write(f"- {item}")

            frame_times = visual.get("frame_timestamps", [])
            if frame_times:
                st.caption("Sampled frames: " + ", ".join(frame_times))

        st.subheader("Audio Review")
        st.write(audio.get("summary", "No audio review generated."))

        audio_left, audio_right = st.columns(2)

        with audio_left:
            if audio.get("strengths"):
                st.write("**Strengths**")
                for item in audio["strengths"]:
                    st.write(f"- {item}")

            if audio.get("issues"):
                st.write("**Issues**")
                for item in audio["issues"]:
                    st.write(f"- {item}")

        with audio_right:
            if audio.get("suggestions"):
                st.write("**Suggestions**")
                for item in audio["suggestions"]:
                    st.write(f"- {item}")

            if audio.get("timestamp_notes"):
                st.write("**Timestamp Notes**")
                for item in audio["timestamp_notes"]:
                    st.write(f"- {item}")

        with st.expander("Transcript"):
            st.write(transcript or "No transcript generated.")
            
            if rows:
                df = pd.DataFrame(rows)
                styled_df = df.style.map(color_severity, subset=["Severity"])
                st.subheader("QC Board")
                st.dataframe(styled_df, use_container_width=True, height=520)
                st.download_button(
                    "Download Report (CSV)",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="video_qc_report.csv",
                    mime="text/csv",
                )
            else:
                st.info("No QC rows returned.")


else:
    st.info("Upload a video to start.")