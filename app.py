# app.py
import streamlit as st
from pathlib import Path
import tempfile
import datetime as dt

from core import transcribe_audio, generate_minutes, generate_next_agenda
from db import MinutesDB
from templates import MINUTES_PROMPT, AGENDA_PROMPT

# 先ほど作成したユーティリティをインポート
from audio_utils import convert_m4a_to_mp3

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
uploaded_audio = st.file_uploader(
    "🎤 会議音声（mp3/wav/m4a 等）をアップロード", 
    type=["mp3", "wav", "m4a"]
)

if uploaded_audio:
    # 拡張子を調べる
    ext = Path(uploaded_audio.name).suffix.lower()

    if ext == ".m4a":
        # M4A → MP3 に変換
        st.info("M4A ファイルが検出されました。MP3 に変換中...")
        try:
            mp3_bytes, mp3_filename = convert_m4a_to_mp3(
                input_bytes=uploaded_audio.read(),
                original_filename=uploaded_audio.name
            )
        except Exception as e:
            st.error(f"変換エラー:\n{e}")
            st.stop()

        # 変換後の MP3 を一時ファイルに保存して、再生および transcribe に渡す
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tf_mp3:
            tf_mp3.write(mp3_bytes)
            audio_path = Path(tf_mp3.name)
        st.success(f"M4A → MP3 変換完了: {mp3_filename}")

    else:
        # MP3/WAV はそのままローカル一時ファイルに書き出し
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
            tf.write(uploaded_audio.read())
            audio_path = Path(tf.name)

    # 生成された audio_path を再生コンポーネントに渡す
    st.audio(str(audio_path), format=f"audio/{audio_path.suffix.replace('.', '')}")

    # ここから文字起こし／議事録生成のボタン操作
    if st.button("🔁 文字起こしを実行"):
        with st.spinner("OpenAI Whisper で文字起こし中…"):
            transcript_text = transcribe_audio(audio_path)
        st.success("文字起こし完了！")
        st.text_area("📝 文字起こし結果（編集可）", value=transcript_text, key="transcript_box")
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
