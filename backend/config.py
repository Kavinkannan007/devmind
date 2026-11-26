import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def setting(key, default=""):
    return os.getenv(key, default).strip()


def limit(key, default, maximum):
    value = int(setting(key, str(default)))
    if not 1 <= value <= maximum:
        raise ValueError(f"{key} must be between 1 and {maximum}")
    return value
