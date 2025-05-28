import streamlit as st
from pathlib import Path
import tempfile
import datetime as dt
import openai

from core import transcribe_audio, generate_minutes, generate_next_agenda
from db import MinutesDB
from templates import MINUTES_PROMPT, AGENDA_PROMPT

st.set_page_config(page_title="議事録作成ツール", page_icon="📝", layout="wide")

st.title("📝 議事録作成ツール（オフライン）")

# ─────────────────────────────────────────────
# DB 初期化
# ─────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
db = MinutesDB(DATA_DIR / "minutes.sqlite3")

# ─────────────────────────────────────────────
# UI – アップロード
# ─────────────────────────────────────────────
uploaded_audio = st.file_uploader("🎤 会議音声（mp3/wav/m4a 等）をアップロード", type=["mp3", "wav", "m4a"])

if uploaded_audio:
    # 一時ファイルへ保存
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_audio.name).suffix) as tf:
        tf.write(uploaded_audio.read())
        audio_path = Path(tf.name)

    st.audio(str(audio_path), format="audio/wav")
    if st.button("🔁 文字起こしを実行"):
        with st.spinner("OpenAI Whisper で文字起こし中…"):
            transcript_text = transcribe_audio(audio_path)
        st.success("文字起こし完了！")
        st.text_area("📝 文字起こし結果（編集可）", value=transcript_text, key="transcript_box", height=300)
else:
    st.info("まず音声ファイルをアップロードしてください。")
    st.stop()

# transcript_box の内容を取得
transcript_text = st.session_state.get("transcript_box", "")

col1, col2 = st.columns(2)
with col1:
    if st.button("📄 議事録を生成"):
        if not transcript_text.strip():
            st.warning("文字起こしを先に行ってください。")
        else:
            with st.spinner("ローカル LLM で議事録生成中…"):
                minutes_md = generate_minutes(transcript_text, MINUTES_PROMPT)
            st.markdown(minutes_md, unsafe_allow_html=True)

            # DB 保存
            title = f"{dt.datetime.now():%Y-%m-%d %H:%M} の会議"
            db.save_minutes(title, transcript_text, minutes_md)
            st.success("議事録を保存しました。")

with col2:
    if st.button("🗓️ 次回アジェンダを生成"):
        if not transcript_text.strip():
            st.warning("文字起こしを先に行ってください。")
        else:
            with st.spinner("ローカル LLM でアジェンダ生成中…"):
                agenda_md = generate_next_agenda(transcript_text, AGENDA_PROMPT, db)
            st.markdown(agenda_md, unsafe_allow_html=True)

st.divider()
st.subheader("📚 過去の議事録")
for rec in db.fetch_all_minutes():
    with st.expander(rec["title"]):
        st.markdown(rec["minutes_md"], unsafe_allow_html=True)
