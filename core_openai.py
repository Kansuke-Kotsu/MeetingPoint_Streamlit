"""core.py – OpenAI Whisper & GPT-4o-mini を使った
   文字起こし・議事録 / アジェンダ生成ロジック
"""
from pathlib import Path
import os
import datetime as dt

import openai              # pip install openai
#from jinja2 import Template

# ─────────────────────────────────────────
# OpenAI API キー & 共通設定
# ─────────────────────────────────────────
import streamlit as st
openai.api_key = os.getenv("OPENAI_API_KEY") or st.secrets["OPENAI_API_KEY"]

TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe" 
GPT_MODEL        = "gpt-4o-mini"

# ─────────────────────────────────────────
# 1) Whisper API で文字起こし
#    ※ ffmpeg 変換に失敗したらそのまま送信
# ─────────────────────────────────────────
def transcribe_audio(audio_path: Path, *, lang: str = "ja") -> str:
    """音声ファイルを文字起こし  
       - ffmpeg で WAV 化を試みる  
       - 失敗したら元ファイルをそのまま Whisper へ
    """
    audio_to_send = audio_path
    with open(audio_to_send, "rb") as f:
        resp = openai.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=f,
            language=lang,
            response_format="text",
        )
    return resp  # str
#    resp = resp["text"].strip()  # str


# ─────────────────────────────────────────
# 2) GPT-4o-mini で要約
# ─────────────────────────────────────────
def generate_minutes(transcript: str, template_str: str) -> str:
    prompt = (
        "あなたは日本語の議事録作成アシスタントです。"
        "以下のテンプレートに従って、文字起こしデータを要約して議事録としてまとめてください。"
    )
    resp = openai.chat.completions.create(
            model=GPT_MODEL,
            messages=[prompt, 
                  "\n".join(template_str),
                  "\n以下文字起こしデータ：",
                  "\n".join(transcript)],
        )
    
    return resp.choices[0].message.content.strip()

# ─────────────────────────────────────────
# 3) GPT-4o-mini で次回アジェンダ生成
# ─────────────────────────────────────────
def generate_next_agenda(transcript: str, template_str: str, db) -> str:
    last = db.fetch_latest_minutes()
    prev_md = last.get("minutes_md") if last else None
    
    prompt = (
        "あなたはプロのファシリテーターです。"
        "会議文字起こしと（あれば）前回議事録をもとに、"
        "## 次回アジェンダ と ## 宿題・タスク を Markdown 形式で作成してください。"
        "- 宿題には担当者・期日を含める"
    )

    resp = openai.chat.completions.create(
        model=GPT_MODEL,
        messages=[prompt, 
                  "\n".join(template_str),
                  "\n以下文字起こしデータ：",
                  "\n".join(transcript)
                  ] + ([prev_md] if prev_md else []),
    )
    return resp.choices[0].message.content.strip()
