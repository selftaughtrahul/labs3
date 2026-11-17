"""Load a local .env file without overriding real environment variables."""

from pathlib import Path


def load_local_env() -> None:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_file)
