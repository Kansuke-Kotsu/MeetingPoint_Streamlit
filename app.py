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
    with st.spinner("ファイルアップロード中…"):
        audio_bytes = uploaded_audio.read()
    ext = Path(uploaded_audio.name).suffix.lower()
    if ext == ".m4a":
        with st.spinner("M4A→MP3変換中…"):
            mp3_bytes, _ = convert_m4a_to_mp3(input_bytes=audio_bytes, original_filename=uploaded_audio.name)
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tf.write(mp3_bytes)
        tf.close()
        st.session_state['audio_path'] = Path(tf.name)
    else:
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tf.write(audio_bytes)
        tf.close()
        st.session_state['audio_path'] = Path(tf.name)
    st.session_state['audio_converted'] = True

audio_path = st.session_state['audio_path']
st.audio(str(audio_path), format=f"audio/{audio_path.suffix.replace('.', '')}")

# 実行ボタン
if st.button("🔄 リアルタイム処理開始（OpenAI & Gemini）"):
    # カラム & プレースホルダ
    col_oa, col_gm = st.columns(2)
    oa_status = col_oa.empty()
    gm_status = col_gm.empty()

    # チャンク分割
    oa_status.text("[OpenAI] チャンク分割中…")
    gm_status.text("[Gemini] チャンク分割中…")
    try:
        chunk_paths = split_mp3_to_chunks(audio_path)
    except Exception as e:
        oa_status.error(f"チャンク分割エラー: {e}")
        gm_status.error(f"チャンク分割エラー: {e}")
        st.stop()
    oa_status.success(f"チャンク分割完了：{len(chunk_paths)} 個")
    gm_status.success(f"チャンク分割完了：{len(chunk_paths)} 個")

    # 文字起こし
    transcripts_oa, transcripts_gm = [], []
    t_oa = t_gm = 0.0
    for idx, chunk in enumerate(chunk_paths, start=1):
        oa_status.info(f"[OpenAI] チャンク {idx}/{len(chunk_paths)} を文字起こし中…")
        gm_status.info(f"[Gemini] チャンク {idx}/{len(chunk_paths)} を文字起こし中…")
        start = time.time(); txt_oa = transcribe_audio(chunk).strip(); t_oa += time.time() - start
        start = time.time(); txt_gm = transcribe_audio_gemini(chunk).strip(); t_gm += time.time() - start
        transcripts_oa.append(txt_oa); transcripts_gm.append(txt_gm)
        oa_status.success(f"[OpenAI] チャンク {idx} 完了 ({t_oa:.1f}s)")
        gm_status.success(f"[Gemini] チャンク {idx} 完了 ({t_gm:.1f}s)")
        os.remove(chunk)
    os.remove(audio_path)
    transcript_openai = "\n".join(transcripts_oa)
    transcript_gemini = "\n".join(transcripts_gm)
    oa_status.empty(); gm_status.empty()

    # 生成処理
    oa_status = col_oa.empty(); gm_status = col_gm.empty()
    oa_status.text("[OpenAI] 議事録・アジェンダ生成中…")
    start = time.time(); minutes_oa = generate_minutes_openai(transcript_openai, MINUTES_PROMPT); t_min_oa = time.time() - start
    start = time.time(); agenda_oa = generate_next_agenda_openai(transcript_openai, AGENDA_PROMPT, db); t_ag_oa = time.time() - start
    oa_status.success(f"[OpenAI] 完了 (議事録 {t_min_oa:.1f}s, アジェンダ {t_ag_oa:.1f}s)")

    gm_status.text("[Gemini] 議事録・アジェンダ生成中…")
    start = time.time(); minutes_gm = generate_minutes_gemini(transcript_gemini, MINUTES_PROMPT); t_min_gm = time.time() - start
    start = time.time(); agenda_gm = generate_next_agenda_gemini(transcript_gemini, AGENDA_PROMPT, db); t_ag_gm = time.time() - start
    gm_status.success(f"[Gemini] 完了 (議事録 {t_min_gm:.1f}s, アジェンダ {t_ag_gm:.1f}s)")

    # タブ切り替えで表示
    tabs = st.tabs(["OpenAI", "Gemini"])
    with tabs[0]:
        st.metric("Whisper Time", f"{t_oa:.1f}s")
        st.metric("Minutes Time", f"{t_min_oa:.1f}s")
        st.metric("Agenda Time", f"{t_ag_oa:.1f}s")
        st.subheader("文字起こし (OpenAI)")
        st.text_area("", transcript_openai, height=200)
        st.subheader("📄 議事録 (OpenAI)")
        st.markdown(minutes_oa, unsafe_allow_html=True)
        st.subheader("🗓️ アジェンダ (OpenAI)")
        st.markdown(agenda_oa, unsafe_allow_html=True)
    with tabs[1]:
        st.metric("Whisper Time", f"{t_gm:.1f}s")
        st.metric("Minutes Time", f"{t_min_gm:.1f}s")
        st.metric("Agenda Time", f"{t_ag_gm:.1f}s")
        st.subheader("文字起こし (Gemini)")
        st.text_area("", transcript_gemini, height=200)
        st.subheader("📄 議事録 (Gemini)")
        st.markdown(minutes_gm, unsafe_allow_html=True)
        st.subheader("🗓️ アジェンダ (Gemini)")
        st.markdown(agenda_gm, unsafe_allow_html=True)

# 過去の議事録
st.divider()
st.subheader("📚 過去の議事録")
for rec in db.fetch_all_minutes():
    with st.expander(rec["title"]):
        st.markdown(rec["minutes_md"], unsafe_allow_html=True)
