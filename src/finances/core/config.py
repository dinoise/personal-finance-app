from pathlib import Path

__version__ = "0.1.0"

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    db_path: Path = _ROOT / "data" / "finance.db"
    config_dir: Path = _ROOT / "src" / "finances" / "config"
    data_dir: Path = _ROOT / "data"

    debug: bool = False


settings = Settings()
