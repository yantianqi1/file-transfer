import math
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.config import AppConfig
from app.security import generate_token, hash_secret, verify_secret
from app.storage import merge_chunks, normalize_relative_path, safe_join, write_chunk


DEFAULT_SESSION_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _dict(row: sqlite3.Row) -> dict:
    return dict(row)


def is_initialized(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone()
    return row is not None


def complete_setup(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    uploads_dir: Path,
    chunks_dir: Path,
    public_url: str,
    default_max_bytes: int,
) -> None:
    if is_initialized(conn):
        raise ValueError("Application is already initialized")
    if not username.strip():
        raise ValueError("Username is required")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if default_max_bytes <= 0:
        raise ValueError("Default upload limit must be positive")

    conn.execute(
        "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
        (username.strip(), hash_secret(password)),
    )
    conn.execute(
        """
        INSERT INTO app_settings
            (id, uploads_dir, chunks_dir, public_url, default_max_bytes)
        VALUES
            (1, ?, ?, ?, ?)
        """,
        (str(uploads_dir), str(chunks_dir), public_url.strip(), default_max_bytes),
    )
    conn.commit()


def _normalize_public_url(public_url: str) -> str:
    return public_url.strip().rstrip("/")


def get_app_settings(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
    if row is None:
        raise ValueError("Application settings not found")
    return _dict(row)


def update_app_settings(
    conn: sqlite3.Connection,
    public_url: str,
    default_max_bytes: int,
) -> dict:
    if default_max_bytes <= 0:
        raise ValueError("Default upload limit must be positive")
    conn.execute(
        """
        UPDATE app_settings
        SET public_url = ?, default_max_bytes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
        """,
        (_normalize_public_url(public_url), default_max_bytes),
    )
    conn.commit()
    return get_app_settings(conn)


def login_admin(conn: sqlite3.Connection, username: str, password: str) -> Optional[str]:
    row = conn.execute(
        "SELECT id, password_hash FROM admin_users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None or not verify_secret(password, row["password_hash"]):
        return None

    token = generate_token(32)
    conn.execute(
        """
        INSERT INTO admin_sessions (token_hash, admin_user_id, expires_at)
        VALUES (?, ?, ?)
        """,
        (hash_secret(token), row["id"], _iso(_utcnow() + timedelta(hours=DEFAULT_SESSION_HOURS))),
    )
    conn.commit()
    return token


def get_admin_by_session(conn: sqlite3.Connection, token: str) -> Optional[dict]:
    rows = conn.execute(
        """
        SELECT s.token_hash, s.expires_at, u.id, u.username
        FROM admin_sessions s
        JOIN admin_users u ON u.id = s.admin_user_id
        """
    ).fetchall()
    now = _utcnow()
    for row in rows:
        if verify_secret(token, row["token_hash"]):
            expires_at = _parse_iso(row["expires_at"])
            if expires_at is None or expires_at <= now:
                return None
            return {"id": row["id"], "username": row["username"]}
    return None


def create_upload_key(
    conn: sqlite3.Connection,
    label: str,
    plain_key: str,
    max_total_bytes: int,
    destination_subdir: str,
    allow_folder_upload: bool,
    expires_at: Optional[str],
) -> dict:
    if not label.strip():
        raise ValueError("Label is required")
    if len(plain_key) < 4:
        raise ValueError("Upload key is too short")
    if max_total_bytes <= 0:
        raise ValueError("Upload limit must be positive")
    normalized_subdir = ""
    if destination_subdir.strip():
        normalized_subdir = normalize_relative_path(destination_subdir)

    cursor = conn.execute(
        """
        INSERT INTO upload_keys
            (key_hash, label, expires_at, max_total_bytes, destination_subdir, allow_folder_upload)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            hash_secret(plain_key),
            label.strip(),
            expires_at,
            max_total_bytes,
            normalized_subdir,
            1 if allow_folder_upload else 0,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM upload_keys WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _dict(row)


def create_upload_link(
    conn: sqlite3.Connection,
    label: str,
    max_total_bytes: int,
    destination_subdir: str,
    allow_folder_upload: bool,
    expires_at: Optional[str],
) -> dict:
    settings = get_app_settings(conn)
    token = generate_token(36)
    record = create_upload_key(
        conn,
        label=label,
        plain_key=token,
        max_total_bytes=max_total_bytes,
        destination_subdir=destination_subdir,
        allow_folder_upload=allow_folder_upload,
        expires_at=expires_at,
    )
    public_url = _normalize_public_url(settings["public_url"])
    upload_url = f"{public_url}/u/{token}" if public_url else f"/u/{token}"
    return {
        "token": token,
        "upload_url": upload_url,
        "record": record,
    }


def list_upload_keys(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, label, status, expires_at, max_total_bytes, destination_subdir,
               allow_folder_upload, created_at
        FROM upload_keys
        ORDER BY id DESC
        """
    ).fetchall()
    return [_dict(row) for row in rows]


def validate_upload_key(conn: sqlite3.Connection, plain_key: str) -> Optional[dict]:
    rows = conn.execute("SELECT * FROM upload_keys WHERE status = 'active'").fetchall()
    now = _utcnow()
    for row in rows:
        expires_at = _parse_iso(row["expires_at"])
        if expires_at is not None and expires_at <= now:
            continue
        if verify_secret(plain_key, row["key_hash"]):
            return _dict(row)
    return None


def disable_upload_key(conn: sqlite3.Connection, upload_key_id: int) -> None:
    conn.execute(
        "UPDATE upload_keys SET status = 'disabled' WHERE id = ?",
        (upload_key_id,),
    )
    conn.commit()


def delete_upload_key(conn: sqlite3.Connection, upload_key_id: int) -> None:
    conn.execute("DELETE FROM upload_keys WHERE id = ?", (upload_key_id,))
    conn.commit()


def _key_received_total(conn: sqlite3.Connection, upload_key_id: int) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(size_bytes), 0) AS total
        FROM upload_files
        WHERE upload_key_id = ?
        """,
        (upload_key_id,),
    ).fetchone()
    return int(row["total"])


def create_upload_file(
    conn: sqlite3.Connection,
    upload_key: dict,
    file_name: str,
    relative_path: str,
    size_bytes: int,
    chunk_size: int,
    file_identifier: Optional[str] = None,
) -> dict:
    if size_bytes <= 0:
        raise ValueError("File size must be positive")
    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")

    normalized_path = normalize_relative_path(relative_path or file_name)
    if not bool(upload_key["allow_folder_upload"]) and "/" in normalized_path:
        normalized_path = normalize_relative_path(Path(normalized_path).name)

    normalized_identifier = (file_identifier or "").strip() or None
    if normalized_identifier:
        existing = conn.execute(
            """
            SELECT * FROM upload_files
            WHERE upload_key_id = ?
              AND file_identifier = ?
              AND file_name = ?
              AND relative_path = ?
              AND size_bytes = ?
              AND status != 'completed'
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                upload_key["id"],
                normalized_identifier,
                file_name,
                normalized_path,
                size_bytes,
            ),
        ).fetchone()
        if existing is not None:
            if existing["status"] == "stopped":
                conn.execute(
                    "UPDATE upload_files SET status = 'waiting' WHERE id = ?",
                    (existing["id"],),
                )
                conn.commit()
                return get_upload_file(conn, existing["id"])
            return _dict(existing)

    if _key_received_total(conn, upload_key["id"]) + size_bytes > upload_key["max_total_bytes"]:
        raise ValueError("Upload key size limit exceeded")

    total_chunks = math.ceil(size_bytes / chunk_size)
    cursor = conn.execute(
        """
        INSERT INTO upload_files
            (upload_key_id, file_identifier, file_name, relative_path, size_bytes, chunk_size, total_chunks)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            upload_key["id"],
            normalized_identifier,
            file_name,
            normalized_path,
            size_bytes,
            chunk_size,
            total_chunks,
        ),
    )
    upload_file_id = cursor.lastrowid
    for index in range(total_chunks):
        expected = chunk_size
        if index == total_chunks - 1:
            expected = size_bytes - (chunk_size * (total_chunks - 1))
        conn.execute(
            """
            INSERT INTO upload_chunks
                (upload_file_id, chunk_index, expected_size)
            VALUES (?, ?, ?)
            """,
            (upload_file_id, index, expected),
        )
    conn.commit()
    return get_upload_file(conn, upload_file_id)


def get_upload_file(conn: sqlite3.Connection, upload_file_id: int) -> dict:
    row = conn.execute("SELECT * FROM upload_files WHERE id = ?", (upload_file_id,)).fetchone()
    if row is None:
        raise ValueError("Upload file not found")
    return _dict(row)


def get_missing_chunks(conn: sqlite3.Connection, upload_file_id: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT chunk_index FROM upload_chunks
        WHERE upload_file_id = ? AND status != 'received'
        ORDER BY chunk_index
        """,
        (upload_file_id,),
    ).fetchall()
    return [int(row["chunk_index"]) for row in rows]


def receive_chunk(
    config: AppConfig,
    conn: sqlite3.Connection,
    upload_file_id: int,
    chunk_index: int,
    body: bytes,
) -> dict:
    upload_file = get_upload_file(conn, upload_file_id)
    if upload_file["status"] == "stopped":
        raise ValueError("Upload has been stopped")
    if upload_file["status"] == "completed":
        return upload_file
    chunk = conn.execute(
        """
        SELECT * FROM upload_chunks
        WHERE upload_file_id = ? AND chunk_index = ?
        """,
        (upload_file_id, chunk_index),
    ).fetchone()
    if chunk is None:
        raise ValueError("Chunk not found")
    if len(body) != int(chunk["expected_size"]):
        raise ValueError("Chunk size mismatch")

    write_chunk(config.chunks_dir, upload_file["upload_key_id"], upload_file_id, chunk_index, body)
    conn.execute(
        """
        UPDATE upload_chunks
        SET received_size = ?, status = 'received', updated_at = CURRENT_TIMESTAMP
        WHERE upload_file_id = ? AND chunk_index = ?
        """,
        (len(body), upload_file_id, chunk_index),
    )
    received = conn.execute(
        """
        SELECT COALESCE(SUM(received_size), 0) AS total
        FROM upload_chunks
        WHERE upload_file_id = ? AND status = 'received'
        """,
        (upload_file_id,),
    ).fetchone()["total"]
    conn.execute(
        "UPDATE upload_files SET received_bytes = ?, status = 'uploading' WHERE id = ?",
        (received, upload_file_id),
    )

    missing = get_missing_chunks(conn, upload_file_id)
    if missing:
        conn.commit()
        return get_upload_file(conn, upload_file_id)

    key = conn.execute(
        "SELECT * FROM upload_keys WHERE id = ?",
        (upload_file["upload_key_id"],),
    ).fetchone()
    destination_relative = upload_file["relative_path"]
    if key["destination_subdir"]:
        destination_relative = f"{key['destination_subdir']}/{destination_relative}"
    destination = safe_join(config.uploads_dir, destination_relative)
    written = merge_chunks(
        config.chunks_dir,
        upload_file["upload_key_id"],
        upload_file_id,
        upload_file["total_chunks"],
        destination,
    )
    if written != upload_file["size_bytes"]:
        raise ValueError("Merged file size mismatch")

    conn.execute(
        """
        UPDATE upload_files
        SET status = 'completed',
            received_bytes = ?,
            destination_path = ?,
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (written, str(destination), upload_file_id),
    )
    conn.commit()
    return get_upload_file(conn, upload_file_id)


def stop_upload_file(conn: sqlite3.Connection, upload_file_id: int) -> dict:
    upload_file = get_upload_file(conn, upload_file_id)
    if upload_file["status"] != "completed":
        conn.execute(
            "UPDATE upload_files SET status = 'stopped' WHERE id = ?",
            (upload_file_id,),
        )
        conn.commit()
    return get_upload_file(conn, upload_file_id)


def delete_upload_file_record(
    config: AppConfig,
    conn: sqlite3.Connection,
    upload_file_id: int,
    delete_file: bool,
) -> None:
    upload_file = get_upload_file(conn, upload_file_id)
    if delete_file and upload_file["destination_path"]:
        destination = Path(upload_file["destination_path"])
        try:
            upload_root = config.uploads_dir.resolve()
            destination_resolved = destination.resolve()
            if upload_root == destination_resolved or upload_root in destination_resolved.parents:
                destination.unlink(missing_ok=True)
        except FileNotFoundError:
            pass

    chunk_dir = config.chunks_dir / str(upload_file["upload_key_id"]) / str(upload_file_id)
    shutil.rmtree(chunk_dir, ignore_errors=True)
    conn.execute("DELETE FROM upload_files WHERE id = ?", (upload_file_id,))
    conn.commit()


def list_upload_records(conn: sqlite3.Connection, upload_key_id: Optional[int] = None) -> list[dict]:
    if upload_key_id is None:
        rows = conn.execute(
            "SELECT * FROM upload_files ORDER BY id DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM upload_files WHERE upload_key_id = ? ORDER BY id DESC",
            (upload_key_id,),
        ).fetchall()
    return [_dict(row) for row in rows]
