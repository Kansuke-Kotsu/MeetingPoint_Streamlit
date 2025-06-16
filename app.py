import streamlit as st
from pathlib import Path
import tempfile
import datetime as dt
import os
import time

from core_openai import transcribe_audio, generate_minutes as generate_minutes_openai, generate_next_agenda as generate_next_agenda_openai
from core_gemini import transcribe_audio as transcribe_audio_gemini, generate_minutes as generate_minutes_gemini, generate_next_agenda as generate_next_agenda_gemini
from db import MinutesDB
from templates import MINUTES_PROMPT, AGENDA_PROMPT
from audio_utils import convert_m4a_to_mp3, split_mp3_to_chunks

st.set_page_config(page_title="議事録作成ツール", page_icon="📝", layout="wide")
st.title("📝 議事録作成ツール（OpenAI vs Gemini 比較・タブ表示）")

# DB 初期化
data_dir = Path(__file__).parent / "data"
data_dir.mkdir(exist_ok=True)
db = MinutesDB(data_dir / "minutes.sqlite3")

# ファイルアップロード
uploaded_audio = st.file_uploader("🎤 会議音声（mp3/m4a 等）をアップロード", type=["mp3", "m4a"])
if not uploaded_audio:
    st.info("まず音声ファイルをアップロードしてください。")
    st.stop()

# 変換（一度だけ）
if not st.session_state.get('audio_converted'):
    with st.spinner("ファイル読み込み＆変換中…"):
        audio_bytes = uploaded_audio.read()
        ext = Path(uploaded_audio.name).suffix.lower()
        if ext == ".m4a":
            mp3_bytes, _ = convert_m4a_to_mp3(input_bytes=audio_bytes, original_filename=uploaded_audio.name)
            suffix = ".mp3"
        else:
            mp3_bytes = audio_bytes
            suffix = ext
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tf.write(mp3_bytes)
        tf.close()
        st.session_state['audio_path'] = Path(tf.name)
        st.session_state['audio_converted'] = True

audio_path = st.session_state['audio_path']
st.audio(str(audio_path), format=f"audio/{audio_path.suffix.replace('.', '')}")

# 実行ボタン
if st.button("🚀 処理開始（OpenAI & Gemini）"):
    with st.spinner("処理中です...しばらくお待ちください"):
        # チャンク分割
        chunk_paths = split_mp3_to_chunks(audio_path)
        # 文字起こし
        transcripts_oa, transcripts_gm = [], []
        for chunk in chunk_paths:
            transcripts_oa.append(transcribe_audio(chunk).strip())
            transcripts_gm.append(transcribe_audio_gemini(chunk).strip())
            os.remove(chunk)
        os.remove(audio_path)
        transcript_openai = "".join(transcripts_oa)
        transcript_gemini = "".join(transcripts_gm)
        # 議事録とアジェンダ生成
        minutes_oa = generate_minutes_openai(transcript_openai, MINUTES_PROMPT)
        agenda_oa = generate_next_agenda_openai(transcript_openai, AGENDA_PROMPT, db)
        minutes_gm = generate_minutes_gemini(transcript_gemini, MINUTES_PROMPT)
        agenda_gm = generate_next_agenda_gemini(transcript_gemini, AGENDA_PROMPT, db)

    # 結果表示
    tabs = st.tabs(["OpenAI", "Gemini"])
    with tabs[0]:
        st.header("OpenAI 結果")
        st.subheader("文字起こし結果")
        st.text_area("", transcript_openai, height=200)
        st.subheader("議事録")
        st.markdown(minutes_oa, unsafe_allow_html=True)
        st.subheader("次回アジェンダ")
        st.markdown(agenda_oa, unsafe_allow_html=True)
        db.save_minutes(f"OpenAI {dt.datetime.now():%Y-%m-%d %H:%M}", transcript_openai, minutes_oa)
    with tabs[1]:
        st.header("Gemini 結果")
        st.subheader("文字起こし結果")
        st.text_area("", transcript_gemini, height=200)
        st.subheader("議事録")
        st.markdown(minutes_gm, unsafe_allow_html=True)
        st.subheader("次回アジェンダ")
        st.markdown(agenda_gm, unsafe_allow_html=True)
        db.save_minutes(f"Gemini {dt.datetime.now():%Y-%m-%d %H:%M}", transcript_gemini, minutes_gm)

# 過去の議事録
st.divider()
st.subheader("📚 過去の議事録")
for rec in db.fetch_all_minutes():
    with st.expander(rec["title"]):
        st.markdown(rec["minutes_md"], unsafe_allow_html=True)
        st.text_area("文字起こしデータ", rec["transcript"], height=200)
        st.caption(f"保存日時: {rec['created_at']:%Y-%m-%d %H:%M}")
# 保存日時の表示
st.caption(f"最終更新日時: {dt.datetime.now():%Y-%m-%d %H:%M}")
# スタイル設定
st.markdown("""
<style>
    .stTextArea textarea {
        font-family: 'Courier New', Courier, monospace;
        font-size: 14px;
    }
    .stMarkdown {
        font-family: 'Arial', sans-serif;
        line-height: 1.6;
    }
    .stExpanderHeader {
        font-weight: bold;
        color: #333;
    }
    .stExpanderContent {
        background-color: #f9f9f9;
        padding: 10px;
        border-radius: 5px;
    }
    .stButton {
        background-color: #4CAF50;
        color: white;
        border: none;
        padding: 10px 20px;
        text-align: center;
        text-decoration: none;
        display: inline-block;
        font-size: 16px;
        margin: 4px 2px;
        cursor: pointer;
    }
    .stButton:hover {
        background-color: #45a049;
    }
    .stSpinner {
        color: #4CAF50;
    }
    .stCaption {
        font-size: 12px;
        color: #666;
    }
    .stDivider {
        border-top: 1px solid #ccc;
        margin: 20px 0;
    }
    .stTabs {
        margin-top: 20px;
    }
    .stTabLabel {
        font-weight: bold;
        color: #4CAF50;
    }
    .stTabContent {
        padding: 20px;
        background-color: #f0f0f0;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)