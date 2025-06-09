from pathlib import Path
import os
import datetime as dt
import streamlit as st

# ─────────────────────────────────────────
# Google Gemini API (Google Gen AI SDK) 設定
# ─────────────────────────────────────────
from google import genai
from google.genai import types

# API キー設定 (AI Studio または環境変数)
API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

# モデル設定
# 音声入力対応の Gemini フラッシュモデル
#TRANSCRIBE_MODEL = "gemini-2.0-flash"
TRANSCRIBE_MODEL = "gemini-2.5-flash-preview-05-20"
# テキスト生成・要約・議事録生成用
#GENERATION_MODEL = "gemini-2.0-flash"
GENERATION_MODEL = "gemini-2.5-flash-preview-05-20"


# ─────────────────────────────────────────
# 1) Gemini API で音声ファイルの文字起こし
# ─────────────────────────────────────────
def transcribe_audio(audio_path: Path, *, lang: str = "ja") -> str:
    """音声ファイルを Gemini に送り、テキスト化を取得する"""
    # ファイルサイズが小さい場合は inline、
    # 大きい場合は upload API を使う
    file_size = audio_path.stat().st_size
    if file_size > 20 * 1024 * 1024:
        # 20MB 超はアップロードして参照
        uploaded = client.files.upload(file=str(audio_path))
        audio_input = uploaded
    else:
        data = audio_path.read_bytes()
        mime = f"audio/{audio_path.suffix.lstrip('.')}"
        audio_input = types.Part.from_bytes(data=data, mime_type=mime)

    prompt = f"以下の音声を日本語で文字起こししてください。"
    response = client.models.generate_content(
        model=TRANSCRIBE_MODEL,
        contents=[prompt, audio_input],
    )
    return response.text.strip()

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
    chunks = [text[i:i + chunk_chars] for i in range(0, len(text), chunk_chars)]
    partial_summaries = []

    for idx, chunk in enumerate(chunks, 1):
        user_prompt = f"【Part {idx}/{len(chunks)}】\n{chunk}"
        resp = client.models.generate_content(
            model=GENERATION_MODEL,
            contents=[system_prompt, user_prompt],
            # max_output_tokens 相当は generate_config で設定可 (省略時はデフォルト)
        )
        partial_summaries.append(resp.text.strip())

    if len(partial_summaries) == 1:
        return partial_summaries[0]

    # 再要約フェーズ
    merge_prompt = (
        "先ほど生成した複数の要約を統合し、重複を除外して"
        "3〜7 行の箇条書きに再整理してください。"
    )
    combined = "\n".join(partial_summaries)
    resp = client.models.generate_content(
        model=GENERATION_MODEL,
        contents=[merge_prompt, combined],
    )
    return resp.text.strip()

# ─────────────────────────────────────────
# 3) Gemini API で次回アジェンダ生成
# ─────────────────────────────────────────
def _gpt_next_agenda(transcript: str, prev_minutes_md: str | None) -> str:
    system_prompt = (
        "あなたはプロのファシリテーターです。"
        "会議の文字起こし（および前回議事録）が与えられます。"
        "次回の会議に向けた『次回アジェンダ案』と『宿題・タスク』を日本語 Markdown で整理してください。"
        "- 見出し: ## 次回アジェンダ / ## 宿題・タスク"
        "- 箇条書きは 5〜10 項目程度"
        "- 宿題は担当者・期日を含める"
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
from jinja2 import Template

def generate_minutes(transcript: str, template_str: str) -> str:
    summary = _gpt_summarize(transcript)
    rendered = Template(template_str).render(
        summary=summary,
        now=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return rendered

def generate_next_agenda(transcript: str, template_str: str, db) -> str:
    last = db.fetch_latest_minutes()
    prev_md = last.get("minutes_md") if last else None
    agenda_body = _gpt_next_agenda(transcript, prev_md)
    rendered = Template(template_str).render(
        agenda=agenda_body,
        now=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return rendered
