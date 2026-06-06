import posixpath
import shutil
from pathlib import Path


def normalize_relative_path(path: str) -> str:
    cleaned = path.replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/"):
        raise ValueError("Path must be relative")
    normalized = posixpath.normpath(cleaned)
    if normalized in ("", ".") or normalized.startswith("../") or normalized == "..":
        raise ValueError("Path traversal is not allowed")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Invalid path segment")
    return normalized


def safe_join(root: Path, relative_path: str) -> Path:
    normalized = normalize_relative_path(relative_path)
    root_resolved = root.resolve()
    target = (root / normalized).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise ValueError("Path escapes storage root")
    return target


def chunk_path(chunks_dir: Path, upload_key_id: int, upload_file_id: int, chunk_index: int) -> Path:
    return chunks_dir / str(upload_key_id) / str(upload_file_id) / f"{chunk_index}.part"


def write_chunk(
    chunks_dir: Path,
    upload_key_id: int,
    upload_file_id: int,
    chunk_index: int,
    body: bytes,
) -> Path:
    target = chunk_path(chunks_dir, upload_key_id, upload_file_id, chunk_index)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return target


def merge_chunks(
    chunks_dir: Path,
    upload_key_id: int,
    upload_file_id: int,
    total_chunks: int,
    destination: Path,
) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    temp_destination = destination.with_suffix(destination.suffix + ".partial")
    with temp_destination.open("wb") as output:
        for index in range(total_chunks):
            source = chunk_path(chunks_dir, upload_key_id, upload_file_id, index)
            with source.open("rb") as chunk:
                shutil.copyfileobj(chunk, output)
            written += source.stat().st_size
    temp_destination.replace(destination)
    return written
