from pathlib import Path
import os
import datetime as dt
from typing import Optional

import streamlit as st
# ★ import を変更 ★
from google import genai
from jinja2 import Template

# ─────────────────────────────────────────
# Google Gemini API (Gen AI SDK) 設定
# ─────────────────────────────────────────
API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
# ★ Client を直接初期化 ★
client = genai.Client(api_key=API_KEY)  # :contentReference[oaicite:0]{index=0}

# モデル設定
TRANSCRIBE_MODEL = "gemini-1.5-flash-latest"
GENERATION_MODEL = "gemini-1.5-flash-latest"


# ─────────────────────────────────────────
# 1) Gemini API で音声ファイルの文字起こし
# ─────────────────────────────────────────
def transcribe_audio(audio_path: Path, *, lang: str = "ja") -> str:
    """
    音声ファイルをアップロードし、generate_content で文字起こしを取得する
    """
    # 1) ファイルをアップロード
    myfile = client.files.upload(
        file=str(audio_path),
        # mime_type は省略可。SDK が自動判別します。
    )  # :contentReference[oaicite:1]{index=1}

    # 2) 文字起こしプロンプトを投げる
    prompt = f"言語は{lang}で、以下の音声を文字起こししてください。"
    resp = client.models.generate_content(
        model=TRANSCRIBE_MODEL,
        contents=[prompt, myfile],
    )  # :contentReference[oaicite:2]{index=2}

    text = resp.text or ""
    if not text.strip():
        raise ValueError("文字起こし結果が空です。音声ファイルを確認してください。")
    return text.strip()


# ─────────────────────────────────────────
# 2) Gemini API で要約 (２段階チャンク要約)
# ─────────────────────────────────────────
def _gpt_summarize(text: str, *, chunk_chars: int = 6000) -> str:
    system_prompt = (
        "あなたは日本語の議事録作成アシスタントです。"
        "以下の会議文字起こしを 3〜7 行の箇条書きで簡潔に要約してください。"
    )

    # チャンク分割
    chunks = [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]
    partial = []

    for idx, chunk in enumerate(chunks, start=1):
        resp = client.models.generate_content(
            model=GENERATION_MODEL,
            contents=[
                system_prompt,
                f"【Part {idx}/{len(chunks)}】\n{chunk}"
            ],
        )
        partial.append(resp.text.strip())

    if len(partial) == 1:
        return partial[0]

    # 再要約
    merge_prompt = (
        "先ほどの要約を統合し、重複を除外して"
        "3〜7 行の箇条書きに再整理してください。"
    )
    resp = client.models.generate_content(
        model=GENERATION_MODEL,
        contents=[merge_prompt, "\n".join(partial)],
    )
    return resp.text.strip()


# ─────────────────────────────────────────
# 3) Gemini API で次回アジェンダ生成
# ─────────────────────────────────────────
def _gpt_next_agenda(transcript: str, prev_minutes_md: Optional[str]) -> str:
    system_prompt = (
        "あなたはプロのファシリテーターです。"
        "会議文字起こしと（あれば）前回議事録をもとに、"
        "## 次回アジェンダ と ## 宿題・タスク を Markdown 形式で作成してください。"
        "- 箇条書きは 5〜10 項目程度\n"
        "- 宿題には担当者・期日を含める"
    )
    contents = [system_prompt]
    if prev_minutes_md:
        contents.append(prev_minutes_md)
    contents.append(transcript)

    resp = client.models.generate_content(
        model=GENERATION_MODEL,
        contents=contents,
    )
    return resp.text.strip()


# ─────────────────────────────────────────
# 4) テンプレート適用
# ─────────────────────────────────────────
def generate_minutes(transcript: str, template_str: str) -> str:
    summary = _gpt_summarize(transcript)
    return Template(template_str).render(
        summary=summary,
        now=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def generate_next_agenda(transcript: str, template_str: str, db) -> str:
    last = db.fetch_latest_minutes()
    prev_md = last.get("minutes_md") if last else None
    agenda_body = _gpt_next_agenda(transcript, prev_md)
    return Template(template_str).render(
        agenda=agenda_body,
        now=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
