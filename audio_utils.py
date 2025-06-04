# audio_utils.py
import subprocess
import tempfile
import os
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe

def convert_m4a_to_mp3(input_bytes: bytes, original_filename: str) -> (bytes, str):
    """
    M4Aバイト列をMP3バイト列に変換し、そのバイト列と出力ファイル名を返す。
    変換後は一時ファイルを即削除。
    """
    # 一時的に M4A ファイルを書き出し
    suffix = Path(original_filename).suffix  # ".m4a"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf_in:
        tf_in.write(input_bytes)
        in_path = Path(tf_in.name)

    # 出力先 MP3 のパスを同ディレクトリに確保
    out_path = in_path.with_suffix(".mp3")

    # ffmpeg のパスを取得
    ffmpeg_path = get_ffmpeg_exe()

    # ffmpeg コマンドを構築 (高音質設定)
    cmd = [
        ffmpeg_path,
        "-y",  # 上書き許可
        "-i", str(in_path),
        "-codec:a", "libmp3lame",
        "-q:a", "2",  # 品質パラメータ(2 が高音質の目安)
        str(out_path)
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="ignore") if e.stderr else ""
        raise RuntimeError(f"ffmpegでの変換に失敗しました:\n{stderr}")
    finally:
        # 入力用の一時 M4A は消す
        try:
            os.remove(in_path)
        except:
            pass

    # 変換後の MP3 を読み込み、バイト列として取得
    with open(out_path, "rb") as f_mp3:
        mp3_bytes = f_mp3.read()

    # 生成した MP3 ファイル名 (ダウンロード時に利用)
    mp3_filename = out_path.name

    # 変換後の一時 MP3 も即削除
    try:
        os.remove(out_path)
    except:
        pass

    return mp3_bytes, mp3_filename


def split_mp3_to_chunks(mp3_path: Path, chunk_length_sec: int = 20 * 60) -> list[Path]:
    """
    MP3ファイルを指定した長さ（秒）ごとに分割し、一時ファイルとして保存した Path のリストを返す。
    デフォルトは 25 分（1500 秒）。
    戻り値の各 Path は一時的に生成された .mp3 ファイルであり、不要になったら削除してください。
    """
    ffmpeg_path = get_ffmpeg_exe()

    # 一時ディレクトリを用意して、チャンクをそこに出力する
    tmp_dir = Path(tempfile.mkdtemp(prefix="mp3_chunks_"))

    # 出力ファイルパターン (例: tmp_dir/chunk_000.mp3, chunk_001.mp3, ...)
    out_pattern = str(tmp_dir / "chunk_%03d.mp3")

    # ffmpeg の segment 機能を使って分割
    cmd = [
        ffmpeg_path,
        "-i", str(mp3_path),
        "-f", "segment",
        "-segment_time", str(chunk_length_sec),
        "-c", "copy",
        out_pattern
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="ignore") if e.stderr else ""
        raise RuntimeError(f"ffmpeg でチャンク分割に失敗しました:\n{stderr}")

    # 出力ディレクトリから .mp3 ファイルをソートして取得
    chunk_files = sorted(tmp_dir.glob("chunk_*.mp3"))
    return chunk_files
