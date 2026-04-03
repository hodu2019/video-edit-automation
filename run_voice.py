"""
run_voice.py – Entry point for Voice Video Processor
=====================================================
Usage:
    python run_voice.py
    python run_voice.py --config config/voice_config.json
"""

import asyncio
import os
import sys
import argparse
from pathlib import Path

# UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is importable
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.voice_processor import run_batch

DEFAULT_CONFIG = ROOT / "config" / "voice_config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Voice Video Processor")
    parser.add_argument(
        "--config", "-c",
        default=str(DEFAULT_CONFIG),
        help=f"Path to config JSON (default: {DEFAULT_CONFIG})",
    )
    return parser.parse_args()


def main() -> None:
    os.chdir(ROOT)
    args = parse_args()
    asyncio.run(run_batch(args.config))


if __name__ == "__main__":
    main()
