#!/usr/bin/env python3
"""
Launcher for the Avalon Human-vs-LLM Streamlit platform.

Usage:
    python run_human_llm.py [--port PORT]

This script:
  1. Writes MODEL_CONFIGS to model_configs.json (edit the dict below to add models)
  2. Initializes / resets the SQLite shared-state database
  3. Launches `streamlit run app.py` on the specified port
"""

import os
import sys
import json
import argparse
import subprocess

# =========================================================================== #
#  MODEL CONFIGURATION — edit this section to add your LLM endpoints
# =========================================================================== #

MODEL_CONFIGS = {
    # ---- Example: local vLLM endpoint ----
    "Qwen3-32B": {
        "name": "Qwen3-32B",
        "api_url_config": {
            "api_key": "EMPTY",
            "base_url": "http://172.18.30.165:8815/v1",
        },
        "inference_config": {
            "model": "Qwen3-32B",
            "temperature": 0.7,
            "top_p": 0.8,
            "max_tokens": 8192,
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": False}
            },
        },
    },
    "avalon_sft_1_7B_CoT-FLAT": {
        "name": "avalon_sft_1_7B_CoT-FLAT",
        "api_url_config": {
            "api_key": "EMPTY",
            "base_url": "http://172.18.39.164:8002/v1",
        },
        "inference_config": {
            "model": "avalon_sft_1_7B_CoT-FLAT",
            "temperature": 0.7,
            "top_p": 0.8,
            "max_tokens": 8192,
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": False}
            },
        },
    },
    # Add more models here...
}

# =========================================================================== #

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "model_configs.json")
DB_PATH = os.path.join(PROJECT_ROOT, "game_shared_state.db")


def write_model_configs():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(MODEL_CONFIGS, f, indent=2, ensure_ascii=False)
    print(f"[Init] Model configs written to {CONFIG_PATH}")
    print(f"       Available models: {list(MODEL_CONFIGS.keys())}")


def reset_shared_state():
    sys.path.insert(0, PROJECT_ROOT)
    from shared_state import SharedStateManager
    sm = SharedStateManager(db_path=DB_PATH)
    sm.clear_all()
    print(f"[Init] Shared state database reset: {DB_PATH}")


def launch_streamlit(port: int):
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        os.path.join(PROJECT_ROOT, "app.py"),
        "--server.port", str(port),
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    print(f"\n[Launch] Starting Streamlit on port {port}")
    print(f"         Access URL: http://<your-ip>:{port}")
    print(f"         Command: {' '.join(cmd)}\n")
    subprocess.run(cmd, cwd=PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(description="Launch Avalon Human-vs-LLM Platform")
    parser.add_argument("--port", type=int, default=8501,
                        help="Port for the Streamlit server (default: 8501)")
    args = parser.parse_args()

    write_model_configs()
    reset_shared_state()
    launch_streamlit(args.port)


if __name__ == "__main__":
    main()
