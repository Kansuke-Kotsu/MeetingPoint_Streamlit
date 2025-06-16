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
if st.button("🚀 リアルタイム処理開始（OpenAI & Gemini）"):
    # 全体進捗バー
    total_steps = 2
    overall_progress = st.sidebar.progress(0)

    # チャンク分割
    st.sidebar.write("## ステップ1: チャンク分割")
    try:
        chunk_paths = split_mp3_to_chunks(audio_path)
        st.sidebar.success(f"{len(chunk_paths)} 個のチャンクを作成しました")
    except Exception as e:
        st.sidebar.error(f"チャンク分割エラー: {e}")
        st.stop()
    overall_progress.progress(1 / total_steps)

    # 並列進捗バー
    st.sidebar.write("## ステップ2: 文字起こし＆生成進捗")
    prog_oa = st.sidebar.progress(0)
    prog_gm = st.sidebar.progress(0)

    # 各種タイマー
    transcripts_oa, transcripts_gm = [], []
    t_oa = t_gm = 0.0
    count = len(chunk_paths)

    # 文字起こし
    for idx, chunk in enumerate(chunk_paths, start=1):
        start = time.time()
        txt_oa = transcribe_audio(chunk).strip()
        t_oa += time.time() - start
        start = time.time()
        txt_gm = transcribe_audio_gemini(chunk).strip()
        t_gm += time.time() - start
        transcripts_oa.append(txt_oa)
        transcripts_gm.append(txt_gm)
        prog_oa.progress(idx / count)
        prog_gm.progress(idx / count)
        os.remove(chunk)
    os.remove(audio_path)

    overall_progress.progress(2 / total_steps)
    st.sidebar.success("すべての文字起こしが完了しました！")

    # 統合テキスト
    transcript_openai = "\n".join(transcripts_oa)
    transcript_gemini = "\n".join(transcripts_gm)

    # タブ表示
    tabs = st.tabs(["OpenAI", "Gemini"])

    # OpenAIタブ
    with tabs[0]:
        st.header("OpenAI 結果")
        st.metric("Whisper 時間", f"{t_oa:.1f}s")
        # 議事録生成
        with st.spinner("OpenAI: 議事録生成中…"):
            start = time.time(); minutes_oa = generate_minutes_openai(transcript_openai, MINUTES_PROMPT); dt1 = time.time() - start
        st.metric("Minutes 時間", f"{dt1:.1f}s")
        # アジェンダ生成
        with st.spinner("OpenAI: アジェンダ生成中…"):
            start = time.time(); agenda_oa = generate_next_agenda_openai(transcript_openai, AGENDA_PROMPT, db); dt2 = time.time() - start
        st.metric("Agenda 時間", f"{dt2:.1f}s")
        st.subheader("文字起こし結果")
        st.text_area("", transcript_openai, height=200)
        st.subheader("議事録")
        st.markdown(minutes_oa, unsafe_allow_html=True)
        st.subheader("次回アジェンダ")
        st.markdown(agenda_oa, unsafe_allow_html=True)
        db.save_minutes(f"OpenAI {dt.datetime.now():%Y-%m-%d %H:%M}", transcript_openai, minutes_oa)

    # Geminiタブ
    with tabs[1]:
        st.header("Gemini 結果")
        st.metric("Whisper 時間", f"{t_gm:.1f}s")
        with st.spinner("Gemini: 議事録生成中…"):
            start = time.time(); minutes_gm = generate_minutes_gemini(transcript_gemini, MINUTES_PROMPT); dt3 = time.time() - start
        st.metric("Minutes 時間", f"{dt3:.1f}s")
        with st.spinner("Gemini: アジェンダ生成中…"):
            start = time.time(); agenda_gm = generate_next_agenda_gemini(transcript_gemini, AGENDA_PROMPT, db); dt4 = time.time() - start
        st.metric("Agenda 時間", f"{dt4:.1f}s")
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
