import streamlit as st
from pathlib import Path
import tempfile
import datetime as dt
import os

from core_openai import transcribe_audio, generate_minutes as generate_minutes_openai, generate_next_agenda as generate_next_agenda_openai
from core_gemini import transcribe_audio as transcribe_audio_gemini, generate_minutes as generate_minutes_gemini, generate_next_agenda as generate_next_agenda_gemini
from db import MinutesDB
from templates import MINUTES_PROMPT, AGENDA_PROMPT
from audio_utils import convert_m4a_to_mp3, split_mp3_to_chunks

st.set_page_config(page_title="議事録作成ツール", page_icon="📝", layout="wide")
st.title("📝 議事録作成ツール（OpenAI vs Gemini 比較）")

# DB 初期化
data_dir = Path(__file__).parent / "data"
data_dir.mkdir(exist_ok=True)
db = MinutesDB(data_dir / "minutes.sqlite3")

# ファイルアップロード
uploaded_audio = st.file_uploader("🎤 会議音声（mp3/m4a 等）をアップロード", type=["mp3", "m4a"])
if not uploaded_audio:
    st.info("まず音声ファイルをアップロードしてください。")
    st.stop()

# 読み込み＆形式変換（一度だけ実行）
if not st.session_state.get('audio_converted'):
    with st.spinner("ファイルアップロード中…"):
        audio_bytes = uploaded_audio.read()
    ext = Path(uploaded_audio.name).suffix.lower()
    if ext == ".m4a":
        with st.spinner("M4A→MP3変換中…"):
            try:
                mp3_bytes, mp3_filename = convert_m4a_to_mp3(input_bytes=audio_bytes, original_filename=uploaded_audio.name)
            except Exception as e:
                st.error(f"変換エラー: {e}")
                st.stop()
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tf.write(mp3_bytes)
        tf.close()
        st.session_state['audio_path'] = Path(tf.name)
        st.success(f"変換完了: {mp3_filename}")
    else:
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tf.write(audio_bytes)
        tf.close()
        st.session_state['audio_path'] = Path(tf.name)
    st.session_state['audio_converted'] = True

audio_path = st.session_state['audio_path']
st.audio(str(audio_path), format=f"audio/{audio_path.suffix.replace('.', '')}")

# 一連処理ボタン
if st.button("🔄 文字起こし＆議事録作成（OpenAI & Gemini 並行）"):
    # チャンク分割（一度だけ）
    if not st.session_state.get('split_done'):
        with st.spinner("チャンク分割中…"):
            try:
                cps = split_mp3_to_chunks(audio_path)
            except Exception as e:
                st.error(f"チャンク分割エラー: {e}")
                os.remove(audio_path)
                st.stop()
        st.session_state['chunk_paths'] = cps
        st.session_state['split_done'] = True
    # 表示
    #st.write("**分割されたチャンクファイル**")
    #for cp in st.session_state['chunk_paths']:
    #    st.write(f"- {cp.name}")

    # 文字起こし（一度だけ）
    if not st.session_state.get('transcript_done'):
        full = ""
        for idx, chunk in enumerate(st.session_state['chunk_paths'], start=1):
            with st.spinner(f"チャンク {idx}/{len(st.session_state['chunk_paths'])} 文字起こし中…"):
                full += transcribe_audio(chunk).strip() + "\n"
            try:
                os.remove(chunk)
            except:
                pass
        os.remove(audio_path)
        st.session_state['full_transcript'] = full
        st.session_state['transcript_done'] = True
        # 文字起こし結果を表示
        st.write("### 文字起こし結果")
        st.text_area("文字起こし結果", value=full, height=300, key="transcript_area")

    transcript = st.session_state['full_transcript']
    if not transcript.strip():
        st.warning("文字起こしが空です。")
    else:
        # 並行生成
        with st.spinner("議事録・アジェンダ生成中…"):
            # OpenAI
            m_oa = generate_minutes_openai(transcript, MINUTES_PROMPT)
            a_oa = generate_next_agenda_openai(transcript, AGENDA_PROMPT, db)
            # Gemini
            m_gm = generate_minutes_gemini(transcript, MINUTES_PROMPT)
            a_gm = generate_next_agenda_gemini(transcript, AGENDA_PROMPT, db)

        # レイアウト
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📄 OpenAI ChatGPT 議事録")
            st.markdown(m_oa, unsafe_allow_html=True)
            st.subheader("🗓️ OpenAI 次回アジェンダ")
            st.markdown(a_oa, unsafe_allow_html=True)
            db.save_minutes(f"OpenAI {dt.datetime.now():%Y-%m-%d %H:%M}", transcript, m_oa)
        with col2:
            st.subheader("📄 Gemini 議事録")
            st.markdown(m_gm, unsafe_allow_html=True)
            st.subheader("🗓️ Gemini 次回アジェンダ")
            st.markdown(a_gm, unsafe_allow_html=True)
            db.save_minutes(f"Gemini {dt.datetime.now():%Y-%m-%d %H:%M}", transcript, m_gm)

# 過去の議事録
st.divider()
st.subheader("📚 過去の議事録")
for rec in db.fetch_all_minutes():
    with st.expander(rec["title"]):
        st.markdown(rec["minutes_md"], unsafe_allow_html=True)
