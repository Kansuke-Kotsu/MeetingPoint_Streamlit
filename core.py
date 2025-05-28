"""core.py – OpenAI Whisper & GPT-4o-mini を使った
   文字起こし・議事録 / アジェンダ生成ロジック
"""
from pathlib import Path
import os
import datetime as dt
import ffmpeg
import textwrap

import openai              # pip install openai
from jinja2 import Template

# ─────────────────────────────────────────
# OpenAI API キー & 共通設定
# ─────────────────────────────────────────
import streamlit as st
openai.api_key = os.getenv("OPENAI_API_KEY") or st.secrets["OPENAI_API_KEY"]

WHISPER_MODEL  = "whisper-1"
GPT_MODEL      = "gpt-4o-mini"

# ─────────────────────────────────────────
# 1) Whisper API で文字起こし
# ─────────────────────────────────────────
def _to_wav(src: Path) -> Path:
    """API 互換の 16 kHz / mono WAV に変換"""
    dst = src.with_suffix(".wav")
    (
        ffmpeg.input(str(src))
            .output(str(dst), acodec="pcm_s16le", ac=1, ar="16k")
            .overwrite_output()
            .run(quiet=True, capture_stdout=True, capture_stderr=True)
    )
    return dst

def transcribe_audio(audio_path: Path, *, lang: str = "ja") -> str:
    wav = _to_wav(audio_path)
    with open(wav, "rb") as f:
        resp = openai.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f,
            language=lang,
            response_format="text",
        )
    return resp   # str

# ─────────────────────────────────────────
# 2) GPT-4o-mini で要約
# ─────────────────────────────────────────
def _gpt_summarize(text: str, *, chunk_chars: int = 6000) -> str:
    """長文をチャンク分割し、部分要約→再要約する 2 段階方式"""
    chunks = [text[i:i + chunk_chars] for i in range(0, len(text), chunk_chars)]
    partial_summaries = []

    for idx, chunk in enumerate(chunks, 1):
        messages = [
            {"role": "system",
             "content": (
                 "あなたは日本語の議事録作成アシスタントです。"
                 "以下の会議文字起こしを 3〜7 行の箇条書きで簡潔に要約してください。"
             )},
            {"role": "user",
             "content": f"【Part {idx}/{len(chunks)}】\n{chunk}"}
        ]
        resp = openai.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            max_tokens=512,
            temperature=0.2,
        )
        partial_summaries.append(resp.choices[0].message.content.strip())

    if len(partial_summaries) == 1:
        return partial_summaries[0]

    # 再要約フェーズ
    messages = [
        {"role": "system",
         "content": (
             "先ほど生成した複数の要約を統合し、重複を除外して "
             "3〜7 行の箇条書きに再整理してください。"
         )},
        {"role": "user", "content": "\n".join(partial_summaries)},
    ]
    resp = openai.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        max_tokens=512,
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()

# ─────────────────────────────────────────
# 3) GPT-4o-mini で次回アジェンダ生成
# ─────────────────────────────────────────
def _gpt_next_agenda(transcript: str, prev_minutes_md: str | None) -> str:
    system_prompt = (
        "あなたはプロのファシリテーターです。"
        "会議の文字起こし（および前回議事録）が与えられます。"
        "次回の会議に向けた『次回アジェンダ案』と『宿題・タスク』を "
        "日本語 Markdown で整理してください。"
        "- 見出し: ## 次回アジェンダ / ## 宿題・タスク\n"
        "- 箇条書きは 5〜10 項目程度\n"
        "- 宿題は担当者・期日を含める"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": transcript},
    ]
    if prev_minutes_md:
        messages.insert(1, {"role": "assistant", "name": "前回議事録", "content": prev_minutes_md})

    resp = openai.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()

# ─────────────────────────────────────────
# 4) テンプレート適用
# ─────────────────────────────────────────
def generate_minutes(transcript: str, template_str: str) -> str:
    summary = _gpt_summarize(transcript)
    rendered = Template(template_str).render(
        summary=summary,
        now=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return rendered

def generate_next_agenda(transcript: str, template_str: str, db) -> str:
    last = db.fetch_latest_minutes()
    prev_md = last["minutes_md"] if last else None
    agenda_body = _gpt_next_agenda(transcript, prev_md)
    rendered = Template(template_str).render(
        agenda=agenda_body,
        now=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return rendered
