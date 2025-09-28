from __future__ import annotations
import os, yaml
from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parents[1] / ".env", override=True)

def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

@dataclass
class EnvCfg:
    base_url: str
    api_key: str

def env_config(cfg) -> EnvCfg:
    env = (os.getenv("RECALL_ENV", "production").strip().lower())
    base_url = cfg["env"]["production_url"] if env == "production" else cfg["env"]["sandbox_url"]
    api_key = os.getenv("RECALL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RECALL_API_KEY is missing. Put it in .env")
    return EnvCfg(base_url=base_url, api_key=api_key)
