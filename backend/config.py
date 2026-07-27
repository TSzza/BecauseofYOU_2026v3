from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SESSION_DIR = DATA_DIR / "sessions"
PROMPT_DIR = ROOT / "prompts"
DESIGN_DIR = ROOT / "game_design"

HOST = "127.0.0.1"
PORT = 8765

# Source-code model configuration.
# Fill API key here when you want the demo to call a real model.
# provider: "mock", "openai", or "deepseek".
MODEL_SETTINGS = {
    "provider": "deepseek",
    "model": "deepseek-v4-pro",
    "api_key": "sk-b802a2f618bc4d1a9fcdbc512779ab8e",
    "base_url": "https://api.deepseek.com/v1",
    "failure_policy": "raise",
}

# Keep this off by default so environment variables do not silently override
# the source-code settings above.
ALLOW_ENV_OVERRIDE = False

if ALLOW_ENV_OVERRIDE:
    HOST = os.getenv("BOY_HOST", HOST)
    PORT = int(os.getenv("BOY_PORT", str(PORT)))
    MODEL_SETTINGS.update({
        "provider": os.getenv("BOY_MODEL_PROVIDER", MODEL_SETTINGS["provider"]),
        "model": os.getenv("BOY_MODEL", MODEL_SETTINGS["model"]),
        "api_key": os.getenv("OPENAI_API_KEY", MODEL_SETTINGS["api_key"]),
        "base_url": os.getenv("OPENAI_BASE_URL", MODEL_SETTINGS["base_url"]),
        "failure_policy": os.getenv("BOY_MODEL_FAILURE_POLICY", MODEL_SETTINGS["failure_policy"]),
    })

MODEL_PROVIDER = str(MODEL_SETTINGS["provider"]).lower()
MODEL_NAME = str(MODEL_SETTINGS["model"])
MODEL_FAILURE_POLICY = str(MODEL_SETTINGS["failure_policy"]).lower()
OPENAI_API_KEY = str(MODEL_SETTINGS["api_key"])
OPENAI_BASE_URL = str(MODEL_SETTINGS["base_url"]).rstrip("/")


def apply_model_settings(settings: dict[str, str]) -> None:
    """Update runtime model settings for tests and explicit in-process tools."""
    global MODEL_PROVIDER, MODEL_NAME, MODEL_FAILURE_POLICY, OPENAI_API_KEY, OPENAI_BASE_URL
    MODEL_SETTINGS.update(settings)
    MODEL_PROVIDER = str(MODEL_SETTINGS["provider"]).lower()
    MODEL_NAME = str(MODEL_SETTINGS["model"])
    MODEL_FAILURE_POLICY = str(MODEL_SETTINGS["failure_policy"]).lower()
    OPENAI_API_KEY = str(MODEL_SETTINGS["api_key"])
    OPENAI_BASE_URL = str(MODEL_SETTINGS["base_url"]).rstrip("/")
