"""
run_videos.py – Entry point for Batch Video Processor
======================================================
Usage:
    python run_videos.py
    python run_videos.py --config config/videos_config.json
"""

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

from src.batch_processor import load_config, run_batch

DEFAULT_CONFIG = ROOT / "config" / "videos_config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch Video Processor")
    parser.add_argument(
        "--config", "-c",
        default=str(DEFAULT_CONFIG),
        help=f"Path to config JSON (default: {DEFAULT_CONFIG})",
    )
    return parser.parse_args()


def main() -> None:
    os.chdir(ROOT)
    args   = parse_args()
    config = load_config(args.config)

    # Validate required assets
    required = [config["background_path"], config["audio_path"]]
    if "text" not in config:
        required.append(config.get("text_path", "text.txt"))
    missing = [p for p in required if not os.path.exists(p)]
    if missing:
        print("[ERR] Missing required files:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)

    run_batch(config)


if __name__ == "__main__":
    main()
