#!/usr/bin/env python3
"""
510K 专属语音生成脚本 —— Edge TTS 神经网络语音版

使用微软 Edge TTS 生成高质量中文播报语音，替代传统 System.Speech 合成。
女声使用 zh-CN-XiaoxiaoNeural（小晓），男声使用 zh-CN-YunxiNeural（云希）。

依赖：
    pip install edge-tts

用法：
    python generate-fifty-k-voice-assets.py
    python generate-fifty-k-voice-assets.py --female-voice zh-CN-XiaoyiNeural
    python generate-fifty-k-voice-assets.py --output-root ./custom_output
"""

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    print("错误：缺少 edge-tts 依赖。请先执行：pip install edge-tts", file=sys.stderr)
    sys.exit(1)


# ─── 语音配置 ───

CLIPS = {
    "510k.mp3": "五十K",
    "true_510k.mp3": "真五十K",
    "club_three_first.mp3": "梅花三先出",
}

PROFILES = {
    "female": {
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "+15%",
        "pitch": "+30Hz",
    },
    "male": {
        "voice": "zh-CN-YunxiNeural",
        "rate": "+15%",
        "pitch": "-30Hz",
    },
}


# ─── 工具函数 ───

def validate_mp3(path: Path) -> None:
    """验证 MP3 文件存在且非空"""
    if not path.exists():
        raise FileNotFoundError(f"生成的音频文件不存在: {path}")

    size = path.stat().st_size
    if size < 100:
        raise ValueError(f"生成的音频文件过小 ({size} 字节): {path}")

    # 检查 MP3 帧同步头（0xFF 0xFB/0xF3/0xF2）或 ID3 标签头
    data = path.read_bytes()[:4]
    is_mp3_frame = len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
    is_id3 = data[:3] == b"ID3"
    if not is_mp3_frame and not is_id3:
        raise ValueError(f"文件不是有效的 MP3 格式: {path}")


# ─── 主流程 ───

async def generate_clip(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: str,
) -> None:
    """使用 Edge TTS 生成单个 MP3 语音文件"""
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch,
        volume="+60%",
    )
    await communicate.save(output_path)


async def main() -> None:
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="510K 专属语音生成器（Edge TTS）")
    parser.add_argument(
        "--output-root",
        default=str(script_dir / ".." / "public" / "static" / "audio" / "fifty_k"),
        help="前端音频输出根目录",
    )
    parser.add_argument(
        "--backend-output-root",
        default=str(script_dir / ".." / ".." / "backend" / "static" / "audio" / "fifty_k"),
        help="后端音频输出根目录",
    )
    parser.add_argument(
        "--female-voice",
        default=PROFILES["female"]["voice"],
        help=f"女声声线 ID（默认：{PROFILES['female']['voice']}）",
    )
    parser.add_argument(
        "--male-voice",
        default=PROFILES["male"]["voice"],
        help=f"男声声线 ID（默认：{PROFILES['male']['voice']}）",
    )
    args = parser.parse_args()

    # 覆盖命令行指定的声线
    profiles = {
        "female": {**PROFILES["female"], "voice": args.female_voice},
        "male": {**PROFILES["male"], "voice": args.male_voice},
    }

    # 构建输出目录列表
    output_roots: list[Path] = []
    for root_str in [args.output_root, args.backend_output_root]:
        if root_str and root_str.strip():
            resolved = Path(root_str).resolve()
            if resolved not in output_roots:
                output_roots.append(resolved)

    if not output_roots:
        print("错误：未指定任何输出目录", file=sys.stderr)
        sys.exit(1)

    # 逐个生成
    generated_files: list[Path] = []

    for profile_name, profile in profiles.items():
        voice = profile["voice"]
        rate = profile["rate"]
        pitch = profile["pitch"]

        print(f"\n─── 生成 {profile_name} 语音（{voice}）───")

        for filename, text in CLIPS.items():
            for root in output_roots:
                target_dir = root / profile_name
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / filename

                print(f"  生成: {text} -> {target_path} ...", end=" ", flush=True)
                await generate_clip(text, voice, rate, pitch, str(target_path))
                generated_files.append(target_path)
                print("[OK]")

    # 验证所有文件
    print("\n─── 验证生成的文件 ───")
    for path in generated_files:
        validate_mp3(path)
        size_kb = path.stat().st_size / 1024
        print(f"  [OK] {path}  ({size_kb:.1f} KB)")

    # 清理旧的 .wav 文件（如果存在）
    print("\n─── 清理旧 WAV 文件 ───")
    old_wav_names = ["510k.wav", "true_510k.wav", "club_three_first.wav"]
    cleaned = 0
    for root in output_roots:
        for profile_name in profiles:
            for old_name in old_wav_names:
                old_path = root / profile_name / old_name
                if old_path.exists():
                    old_path.unlink()
                    print(f"  已删除: {old_path}")
                    cleaned += 1
    if cleaned == 0:
        print("  （无旧文件需要清理）")

    print(f"\n[DONE] {len(generated_files)} 个文件生成并验证完成！")


if __name__ == "__main__":
    asyncio.run(main())
