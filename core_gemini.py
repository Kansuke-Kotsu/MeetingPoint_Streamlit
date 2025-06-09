from pathlib import Path
import os
import datetime as dt
from typing import Optional

import streamlit as st
import google.generativeai as genai
from jinja2 import Template

# ─────────────────────────────────────────
# Google Gemini API (Google Gen AI SDK) 設定
# ─────────────────────────────────────────
API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
client = genai.get_client()

# モデル設定
TRANSCRIBE_MODEL = "gemini-2.5-flash-preview-05-20"
GENERATION_MODEL = "gemini-2.5-flash-preview-05-20"


# ─────────────────────────────────────────
# 1) Gemini API で音声ファイルの文字起こし
# ─────────────────────────────────────────
def transcribe_audio(audio_path: Path, *, lang: str = "ja") -> str:
    """音声ファイルを Gemini に送信して文字起こしを取得する"""
    # ファイル登録
    uploaded = client.file.create(
        file=audio_path,
        file_format="mp3"
    )
    # 音声→テキスト
    result = client.audio.speech_to_text.create(
        model=TRANSCRIBE_MODEL,
        input=uploaded,
        language_code=lang,
        timeout=60,                # 必要に応じて調整
        retry_config={"max_retries": 2}
    )
    transcript = result.transcript or ""
    if not transcript.strip():
        raise ValueError("文字起こし結果が空です。音声ファイルを確認してください。")
    return transcript.strip()


# ─────────────────────────────────────────
# 2) Gemini API で要約 (２段階チャンク要約)
# ─────────────────────────────────────────
def _gpt_summarize(text: str, *, chunk_chars: int = 6000) -> str:
    """長文をチャンク分割し、部分要約→再要約する 2 段階方式"""
    system_prompt = (
        "あなたは日本語の議事録作成アシスタントです。"
        "以下の会議文字起こしを 3〜7 行の箇条書きで簡潔に要約してください。"
    )

    # チャンク分割
    chunks = [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]
    partial_summaries = []

    for idx, chunk in enumerate(chunks, start=1):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"【Part {idx}/{len(chunks)}】\n{chunk}"}
        ]
        resp = client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=messages,
            max_output_tokens=512
        )
        partial_summaries.append(resp.choices[0].message.content.strip())

    # 単一チャンクならそのまま返す
    if len(partial_summaries) == 1:
        return partial_summaries[0]

    # 再要約フェーズ
    merge_prompt = (
        "先ほど生成した複数の要約を統合し、重複を除外して"
        "3〜7 行の箇条書きに再整理してください。"
    )
    combined = "\n".join(partial_summaries)
    messages = [
        {"role": "system", "content": merge_prompt},
        {"role": "user", "content": combined}
    ]
    resp = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=messages,
        max_output_tokens=512
    )
    return resp.choices[0].message.content.strip()


# ─────────────────────────────────────────
# 3) Gemini API で次回アジェンダ生成
# ─────────────────────────────────────────
def _gpt_next_agenda(transcript: str, prev_minutes_md: Optional[str]) -> str:
    system_prompt = (
        "あなたはプロのファシリテーターです。"
        "会議の文字起こし（および前回議事録）が与えられます。"
        "次回の会議に向けた『次回アジェンダ案』と『宿題・タスク』を日本語 Markdown で整理してください。"
        "- 見出し: ## 次回アジェンダ / ## 宿題・タスク\n"
        "- 箇条書きは 5〜10 項目程度\n"
        "- 宿題は担当者・期日を含める"
    )
    messages = [{"role": "system", "content": system_prompt}]
    if prev_minutes_md:
        messages.append({"role": "user", "content": prev_minutes_md})
    messages.append({"role": "user", "content": transcript})

    resp = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=messages,
        max_output_tokens=512
    )
    return resp.choices[0].message.content.strip()


# ─────────────────────────────────────────
# 4) テンプレート適用
# ─────────────────────────────────────────
def generate_minutes(transcript: str, template_str: str) -> str:
    """文字起こし→要約→Jinja2 テンプレート埋め込み"""
    summary = _gpt_summarize(transcript)
    return Template(template_str).render(
        summary=summary,
        now=dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    )


def generate_next_agenda(transcript: str, template_str: str, db) -> str:
    """文字起こし＋過去議事録→次回アジェンダ→Jinja2 テンプレート埋め込み"""
    last = db.fetch_latest_minutes()
    prev_md = last.get("minutes_md") if last else None
    agenda_body = _gpt_next_agenda(transcript, prev_md)
    return Template(template_str).render(
        agenda=agenda_body,
        now=dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    )
