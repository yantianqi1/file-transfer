import sqlite3
from contextlib import contextmanager

from app.config import AppConfig


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    uploads_dir TEXT NOT NULL,
    chunks_dir TEXT NOT NULL,
    public_url TEXT NOT NULL DEFAULT '',
    default_max_bytes INTEGER NOT NULL DEFAULT 107374182400,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash TEXT PRIMARY KEY,
    admin_user_id INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS upload_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    expires_at TEXT,
    max_total_bytes INTEGER NOT NULL,
    destination_subdir TEXT NOT NULL DEFAULT '',
    allow_folder_upload INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS upload_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_key_id INTEGER NOT NULL REFERENCES upload_keys(id) ON DELETE CASCADE,
    file_identifier TEXT,
    file_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    chunk_size INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting',
    received_bytes INTEGER NOT NULL DEFAULT 0,
    destination_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_upload_files_identifier
ON upload_files (upload_key_id, file_identifier);

CREATE TABLE IF NOT EXISTS upload_chunks (
    upload_file_id INTEGER NOT NULL REFERENCES upload_files(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    expected_size INTEGER NOT NULL,
    received_size INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'missing',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (upload_file_id, chunk_index)
);
"""


def connect(config: AppConfig) -> sqlite3.Connection:
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.uploads_dir.mkdir(parents=True, exist_ok=True)
    config.chunks_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(upload_files)").fetchall()
    }
    if "file_identifier" not in columns:
        conn.execute("ALTER TABLE upload_files ADD COLUMN file_identifier TEXT")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_upload_files_identifier
            ON upload_files (upload_key_id, file_identifier)
            """
        )
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
