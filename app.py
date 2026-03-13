import streamlit as st
import pandas as pd
import tempfile

from video_qc import run_video_qc

st.set_page_config(page_title="AI Amendment Bot — QC Board", layout="wide")

st.markdown("### Koocester")
st.title("AI Amendment Bot — QC Board")

st.caption("Upload a video → generate transcript → run QC on spoken content.")


uploaded = st.file_uploader("Upload video", type=["mp4", "mov", "mkv", "mpeg4"])


def color_severity(val):
    if val == "High":
        return "background-color: #ff4b4b; color: white;"
    elif val == "Medium":
        return "background-color: #ffa500; color: black;"
    elif val == "Low":
        return "background-color: #4caf50; color: white;"
    return ""

if uploaded:
    with tempfile.NamedTemporaryFile(delete=False, suffix="." + uploaded.name.split(".")[-1]) as tmp:
        tmp.write(uploaded.getbuffer())
        video_path = tmp.name

    if st.button("Analyze Video"):
        with st.spinner("Transcribing and analyzing video..."):
            rows = run_video_qc(video_path)

        st.success("Analysis complete")
     

        if not rows:
            st.success("No issues found ✅")
        else:
           df = pd.DataFrame(rows)

           styled_df = df.style.applymap(color_severity, subset=["Severity"])
           st.subheader("QC Board")
           st.dataframe(styled_df, use_container_width=True, height=520)
           st.download_button(
                "Download Report (CSV)",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="video_qc_report.csv",
                mime="text/csv"
            )
else:
    st.info("Upload a video to start.")