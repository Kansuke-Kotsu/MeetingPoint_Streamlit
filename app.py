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
st.title("📝 議事録作成ツール（OpenAI vs Gemini 比較・リアルタイム表示）")

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
if st.button("🔄 リアルタイム表示で処理開始（OpenAI & Gemini）"):
    # カラム作成 for リアルタイム更新
    col_oa, col_gm = st.columns(2)
    # プレースホルダー設定
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

    # 両方の文字起こし
    transcripts_oa = []
    transcripts_gm = []
    for idx, chunk in enumerate(chunk_paths, start=1):
        oa_status.info(f"[OpenAI] チャンク {idx}/{len(chunk_paths)} を文字起こし中…")
        gm_status.info(f"[Gemini] チャンク {idx}/{len(chunk_paths)} を文字起こし中…")
        try:
            txt_oa = transcribe_audio(chunk).strip()
        except Exception as e:
            txt_oa = f"【エラー】{e}"
        try:
            txt_gm = transcribe_audio_gemini(chunk).strip()
        except Exception as e:
            txt_gm = f"【エラー】{e}"
        transcripts_oa.append(txt_oa)
        transcripts_gm.append(txt_gm)
        # 更新
        oa_status.success(f"[OpenAI] チャンク {idx} 完了")
        gm_status.success(f"[Gemini] チャンク {idx} 完了")
        # ファイル削除
        os.remove(chunk)

    # 元音声削除
    os.remove(audio_path)

    # 統合
    transcript_openai = "\n".join(transcripts_oa)
    transcript_gemini = "\n".join(transcripts_gm)
    # 表示切り替え
    oa_status.empty()
    gm_status.empty()

    # 文字起こし結果
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.subheader("文字起こし結果 - OpenAI Whisper")
        st.text_area("OpenAI Transcript", value=transcript_openai, height=200)
    with col_t2:
        st.subheader("文字起こし結果 - Gemini Whisper")
        st.text_area("Gemini Transcript", value=transcript_gemini, height=200)

    # 議事録 & アジェンダ生成
    oa_status = col_oa.empty()
    gm_status = col_gm.empty()
    oa_status.text("[OpenAI] 議事録・アジェンダ生成中…")
    gm_status.text("[Gemini] 議事録・アジェンダ生成中…")
    minutes_oa = generate_minutes_openai(transcript_openai, MINUTES_PROMPT)
    agenda_oa = generate_next_agenda_openai(transcript_openai, AGENDA_PROMPT, db)
    minutes_gm = generate_minutes_gemini(transcript_gemini, MINUTES_PROMPT)
    agenda_gm = generate_next_agenda_gemini(transcript_gemini, AGENDA_PROMPT, db)
    oa_status.success("[OpenAI] 生成完了")
    gm_status.success("[Gemini] 生成完了")

    # 結果表示
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📄 OpenAI ChatGPT 議事録")
        st.markdown(minutes_oa, unsafe_allow_html=True)
        st.subheader("🗓️ OpenAI 次回アジェンダ")
        st.markdown(agenda_oa, unsafe_allow_html=True)
        db.save_minutes(f"OpenAI {dt.datetime.now():%Y-%m-%d %H:%M}", transcript_openai, minutes_oa)
    with col2:
        st.subheader("📄 Gemini 議事録")
        st.markdown(minutes_gm, unsafe_allow_html=True)
        st.subheader("🗓️ Gemini 次回アジェンダ")
        st.markdown(agenda_gm, unsafe_allow_html=True)
        db.save_minutes(f"Gemini {dt.datetime.now():%Y-%m-%d %H:%M}", transcript_gemini, minutes_gm)

# 過去の議事録
st.divider()
st.subheader("📚 過去の議事録")
for rec in db.fetch_all_minutes():
    with st.expander(rec["title"]):
        st.markdown(rec["minutes_md"], unsafe_allow_html=True)
