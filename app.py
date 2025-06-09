import streamlit as st
from pathlib import Path
import tempfile
import datetime as dt
import os

from core_python import transcribe_audio, generate_minutes, generate_next_agenda
from db import MinutesDB
from templates import MINUTES_PROMPT, AGENDA_PROMPT

from audio_utils import convert_m4a_to_mp3, split_mp3_to_chunks

st.set_page_config(page_title="議事録作成ツール", page_icon="📝", layout="wide")
st.title("📝 MeetingPoint PoC tool ~beyond NotebookLM~")

# ─────────────────────────────────────────────────
# DB 初期化
# ─────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
db = MinutesDB(DATA_DIR / "minutes.sqlite3")

# ─────────────────────────────────────────────────
# UI – アップロード
# ─────────────────────────────────────────────────
uploaded_audio = st.file_uploader(
    "🎤 会議音声（mp3/m4a 等）をアップロード", 
    type=["mp3", "m4a"]
)

if not uploaded_audio:
    st.info("まず音声ファイルをアップロードしてください。")
    st.stop()

# ファイル読み込み
with st.spinner("ファイルアップロード中…"):
    audio_bytes = uploaded_audio.read()
ext = Path(uploaded_audio.name).suffix.lower()

# M4A → MP3 変換
if ext == ".m4a":
    with st.spinner("ファイル形式変換中…"):
        try:
            mp3_bytes, mp3_filename = convert_m4a_to_mp3(
                input_bytes=audio_bytes,
                original_filename=uploaded_audio.name
            )
        except Exception as e:
            st.error(f"変換エラー:\n{e}")
            st.stop()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tf_mp3:
        tf_mp3.write(mp3_bytes)
        audio_path = Path(tf_mp3.name)
    st.success(f"M4A → MP3 変換完了: {mp3_filename}")
else:
    with st.spinner("ファイル形式保存中…"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
            tf.write(audio_bytes)
            audio_path = Path(tf.name)

# 音声再生
st.audio(str(audio_path), format=f"audio/{audio_path.suffix.replace('.', '')}")

# ─────────────────────────────────────────────────
# 文字起こし＆議事録・アジェンダ作成
# ─────────────────────────────────────────────────
if st.button("🔄 文字起こしを実行＆議事録作成"):
    # チャンク分割
    with st.spinner("音声をチャンクに分割中…"):
        try:
            chunk_paths = split_mp3_to_chunks(audio_path)
        except Exception as e:
            st.error(f"チャンク分割エラー:\n{e}")
            os.remove(audio_path)
            st.stop()
    # チャンク一覧表示
    st.write("**分割されたチャンクファイル一覧**")
    for cp in chunk_paths:
        st.write(f"- {cp.name}")

    full_transcript = ""
    total_chunks = len(chunk_paths)

    # 各チャンク文字起こし
    for idx, chunk_path in enumerate(chunk_paths, start=1):
        with st.spinner(f"AIによってチャンク {idx}/{total_chunks} を解析中…"):
            try:
                part_text = transcribe_audio(chunk_path).strip()
            except Exception as e:
                part_text = f"【エラー】チャンク {idx} の文字起こし失敗:\n{e}"
        # 表示
        #st.markdown(f"---\n### チャンク {idx} `{chunk_path.name}`\n---")
        #st.text_area(f"チャンク {idx} の文字起こし結果", value=part_text, height=150, key=f"chunk_{idx}")
        full_transcript += part_text
        # クリーンアップ
        try:
            os.remove(chunk_path)
        except:
            pass
    # 元音声削除
    try:
        os.remove(audio_path)
    except:
        pass
    st.success("全チャンクの文字起こし完了！")

    # 全文表示
    st.markdown("## 全チャンクをまとめた文字起こし結果")
    transcript_text = st.text_area("📝 まとめ表示（編集可）", value=full_transcript, height=300, key="transcript_full")

    # 議事録・アジェンダ生成
    if transcript_text.strip():
        with st.spinner("AIによって議事録とアジェンダを生成中…"):
            minutes_md = generate_minutes(transcript_text, MINUTES_PROMPT)
            agenda_md = generate_next_agenda(transcript_text, AGENDA_PROMPT, db)

        # 左右表示
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📄 議事録")
            st.markdown(minutes_md, unsafe_allow_html=True)
            # DB 保存
            title = f"{dt.datetime.now():%Y-%m-%d %H:%M} の会議"
            db.save_minutes(title, transcript_text, minutes_md)
            st.success("議事録を保存しました。")
        with col2:
            st.subheader("🗓️ 次回アジェンダ")
            st.markdown(agenda_md, unsafe_allow_html=True)
    else:
        st.warning("文字起こし結果が空です。編集後に再度実行してください。")

# ─────────────────────────────────────────────────
# 過去の議事録
# ─────────────────────────────────────────────────
st.divider()
st.subheader("📚 過去の議事録")
for rec in db.fetch_all_minutes():
    with st.expander(rec["title"]):
        st.markdown(rec["minutes_md"], unsafe_allow_html=True)
