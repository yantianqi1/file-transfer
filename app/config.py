import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    uploads_dir: Path
    config_dir: Path
    chunks_dir: Path
    host: str
    port: int

    @property
    def database_path(self) -> Path:
        return self.config_dir / "app.sqlite3"


def load_config() -> AppConfig:
    return AppConfig(
        uploads_dir=Path(os.environ.get("UPLOADS_DIR", "/data/uploads")),
        config_dir=Path(os.environ.get("CONFIG_DIR", "/data/config")),
        chunks_dir=Path(os.environ.get("CHUNKS_DIR", "/data/chunks")),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
    )
