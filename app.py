# app.py
import streamlit as st
from pathlib import Path
import tempfile
import datetime as dt
import os

from core import transcribe_audio, generate_minutes, generate_next_agenda
from db import MinutesDB
from templates import MINUTES_PROMPT, AGENDA_PROMPT

from audio_utils import convert_m4a_to_mp3, split_mp3_to_chunks

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
    # 1) アップロード中のスピナーを表示してバイト列を読み込む
    with st.spinner("ファイルアップロード中…"):
        audio_bytes = uploaded_audio.read()

    ext = Path(uploaded_audio.name).suffix.lower()

    # 2) M4A → MP3 変換
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

        # 一時ファイルに MP3 を書き出す
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tf_mp3:
            tf_mp3.write(mp3_bytes)
            audio_path = Path(tf_mp3.name)
        st.success(f"M4A → MP3 変換完了: {mp3_filename}")

    else:
        # MP3/WAV はそのまま一時ファイルに保存
        with st.spinner("ファイル形式保存中…"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                tf.write(audio_bytes)
                audio_path = Path(tf.name)

    # 音声を再生コンポーネントに渡す
    st.audio(str(audio_path), format=f"audio/{audio_path.suffix.replace('.', '')}")

    # ─────────────────────────────────────────────
    #  文字起こし処理（チャンク分割→逐次解析→段階的に表示）
    # ─────────────────────────────────────────────
    if st.button("🔁 文字起こしを実行"):
        # 3) チャンク分割中のスピナー
        with st.spinner("音声をチャンクに分割中…"):
            try:
                chunk_paths = split_mp3_to_chunks(audio_path)
            except Exception as e:
                st.error(f"チャンク分割エラー:\n{e}")
                # 元の一時ファイルは削除しておく
                try:
                    os.remove(audio_path)
                except:
                    pass
                st.stop()

        # 分割されたチャンクのファイル名を表示
        st.write("**分割されたチャンクファイル一覧**")
        for cp in chunk_paths:
            st.write(f"- {cp.name}")

        full_transcript = ""  # 全チャンク分を累積保存
        total_chunks = len(chunk_paths)

        # 4) 各チャンクを逐次文字起こしし、結果を都度表示
        for idx, chunk_path in enumerate(chunk_paths, start=1):
            # チャンク解析中のスピナー
            with st.spinner(f"AIによってチャンク {idx}/{total_chunks} を解析中…"):
                try:
                    part_text = transcribe_audio(chunk_path).strip()
                except Exception as e:
                    part_text = f"【エラー発生】チャンク {idx} の文字起こしに失敗:\n{e}"

            # 表示セクション：チャンク名と文字起こし結果
            st.markdown(f"---\n### チャンク {idx} ファイル: `{chunk_path.name}`\n---")
            st.text_area(
                label=f"チャンク {idx} の文字起こし結果",
                value=part_text,
                height=200,
                key=f"chunk_{idx}"
            )

            # 累積させる場合は空行を挟んで追加
            full_transcript += part_text
#            if idx < total_chunks:
#                full_transcript += "\n\n"

            # 解析後のチャンクファイルは削除してクリーンアップ
            try:
                os.remove(chunk_path)
            except:
                pass

        # 最後に元の一時 MP3 ファイルも削除
        try:
            os.remove(audio_path)
        except:
            pass

        st.success("全チャンクの文字起こしが完了しました！")

        # 5) 必要であれば、全体をまとめて表示
        st.markdown("## 全チャンクをまとめた文字起こし結果")
        st.text_area(
            label="📝 まとめ表示（編集可）",
            value=full_transcript,
            key="transcript_full",
            height=300
        )

else:
    st.info("まず音声ファイルをアップロードしてください。")
    st.stop()

# ─────────────────────────────────────────────
# transcript_box の内容を取得
# ─────────────────────────────────────────────
transcript_text = st.session_state.get("transcript_full", "") or st.session_state.get("transcript_box", "")

col1, col2 = st.columns(2)
with col1:
    if st.button("📄 議事録を生成"):
        if not transcript_text.strip():
            st.warning("文字起こしを先に行ってください。")
        else:
            with st.spinner("AIによって議事録を生成中…"):
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
            with st.spinner("AIによって次回アジェンダを生成中…"):
                agenda_md = generate_next_agenda(transcript_text, AGENDA_PROMPT, db)
            st.markdown(agenda_md, unsafe_allow_html=True)

st.divider()
st.subheader("📚 過去の議事録")
for rec in db.fetch_all_minutes():
    with st.expander(rec["title"]):
        st.markdown(rec["minutes_md"], unsafe_allow_html=True)
