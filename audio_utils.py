# audio_utils.py
import subprocess
import tempfile
import os
from pathlib import Path
from imageio_ffmpeg import get_ffmpeg_exe

def convert_m4a_to_mp3(input_bytes: bytes, original_filename: str) -> (bytes, str):
    """
    M4Aバイト列をMP3バイト列に変換し、そのバイト列と出力ファイル名を返す。
    
    :param input_bytes: アップロードされたM4Aファイルのバイト列
    :param original_filename: アップロード時のファイル名 (例: "meeting.m4a")
    :return: (mp3_bytes, mp3_filename)
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
        # ffmpeg 実行
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        # 変換失敗時には例外を投げる
        stderr = e.stderr.decode(errors="ignore") if e.stderr else ""
        raise RuntimeError(f"ffmpegでの変換に失敗しました:\n{stderr}")
    finally:
        # 入力用の一時 M4A は消す (変換前のファイル)
        try:
            os.remove(in_path)
        except:
            pass

    # 変換後の MP3 を読み込み、バイト列として取得
    with open(out_path, "rb") as f_mp3:
        mp3_bytes = f_mp3.read()

    # 生成した MP3 ファイル名 (ダウンロード時に利用)
    mp3_filename = out_path.name

    # 変換後のファイルも削除
    try:
        os.remove(out_path)
    except:
        pass

    return mp3_bytes, mp3_filename
