import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    bot_name: str = os.getenv("BOT_NAME", "Kayra")
    gemini_key: str = os.getenv("GEMINI_API_KEY", "")
    groq_key: str = os.getenv("GROQ_API_KEY", "")
    openrouter_key: str = os.getenv("OPENROUTER_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free")
    data_dir: str = os.getenv("DATA_DIR", "./data")


settings = Settings()
