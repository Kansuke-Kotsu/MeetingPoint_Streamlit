from pathlib import Path
import os
import datetime as dt
from typing import Optional

import streamlit as st
from google import genai
#from jinja2 import Template

# ─────────────────────────────────────────
# Google Gemini API (Gen AI SDK) 設定
# ─────────────────────────────────────────
API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
# ★ Client を直接初期化 ★
client = genai.Client(api_key=API_KEY)  # :contentReference[oaicite:0]{index=0}

# モデル設定
TRANSCRIBE_MODEL = "gemini-2.5-flash-preview-05-20"
GENERATION_MODEL = "gemini-2.5-flash-preview-05-20"


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
        tempreture=0,  # 再現性のため温度を0に設定
    )  # :contentReference[oaicite:2]{index=2}

    text = resp.text or ""
    if not text.strip():
        raise ValueError("文字起こし結果が空です。音声ファイルを確認してください。")
    return text.strip()


# ─────────────────────────────────────────
# 4) テンプレート適用
# ─────────────────────────────────────────
def generate_minutes(transcript: str, template_str: str) -> str:
    prompt = (
        "あなたは日本語の議事録作成アシスタントです。"
        "以下のテンプレートに従って、文字起こしデータを要約して議事録としてまとめてください。"
    )
    resp = client.models.generate_content(
        model=GENERATION_MODEL,
        contents=[prompt, 
                  "\n".join(template_str),
                  "\n以下文字起こしデータ：",
                  "\n".join(transcript)],
        tempreture=0, # 再現性のため温度を0に設定
    )
    return resp.text.strip()

    
   # return Template(template_str).render(
   #     summary=summary,
   #     now=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
   # )


def generate_next_agenda(transcript: str, template_str: str, db) -> str:
    last = db.fetch_latest_minutes()
    prev_md = last.get("minutes_md") if last else None
    
    prompt = (
        "あなたはプロのファシリテーターです。"
        "会議文字起こしと（あれば）前回議事録をもとに、"
        "## 次回アジェンダ と ## 宿題・タスク を Markdown 形式で作成してください。"
        "- 宿題には担当者・期日を含める"
    )
    
    resp = client.models.generate_content(
        model=GENERATION_MODEL,
        contents=[prompt, 
                  "\n".join(template_str),
                  "\n以下文字起こしデータ：",
                  "\n".join(transcript)
                  ] + ([prev_md] if prev_md else []),
    )
    return resp.text.strip()


    
    
    #agenda_body = _gpt_next_agenda(transcript, prev_md)
    #return Template(template_str).render(
    #    agenda=agenda_body,
    #    now=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    #)
# ─────────────────────────────────────────