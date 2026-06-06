import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config import AppConfig, load_config
from app.db import connect, initialize
from app.services import (
    complete_setup,
    create_upload_file,
    create_upload_key,
    create_upload_link,
    delete_upload_key,
    disable_upload_key,
    get_admin_by_session,
    get_app_settings,
    get_upload_file,
    get_missing_chunks,
    is_initialized,
    list_upload_keys,
    list_upload_records,
    login_admin,
    receive_chunk,
    update_app_settings,
    validate_upload_key,
)


STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_CHUNK_SIZE = 64 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        self.status = status
        self.message = message


class FileTransferHandler(BaseHTTPRequestHandler):
    config: AppConfig

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def _dispatch(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api(parsed.path, parse_qs(parsed.query))
            else:
                self._serve_static(parsed.path)
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": "Internal server error", "detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _connection(self):
        conn = connect(self.config)
        initialize(conn)
        return conn

    def _handle_api(self, path: str, query: dict):
        conn = self._connection()
        try:
            if self.command == "GET" and path == "/api/setup/status":
                self._send_json({"initialized": is_initialized(conn)})
                return

            if self.command == "POST" and path == "/api/setup":
                payload = self._read_json()
                complete_setup(
                    conn,
                    username=payload.get("username", ""),
                    password=payload.get("password", ""),
                    uploads_dir=Path(payload.get("uploadsDir") or self.config.uploads_dir),
                    chunks_dir=Path(payload.get("chunksDir") or self.config.chunks_dir),
                    public_url=payload.get("publicUrl", ""),
                    default_max_bytes=int(payload.get("defaultMaxBytes") or 100 * 1024 * 1024 * 1024),
                )
                self._send_json({"ok": True}, HTTPStatus.CREATED)
                return

            if self.command == "POST" and path == "/api/admin/login":
                payload = self._read_json()
                token = login_admin(conn, payload.get("username", ""), payload.get("password", ""))
                if token is None:
                    raise ApiError(HTTPStatus.UNAUTHORIZED, "Invalid username or password")
                self._send_json({"ok": True}, headers={"Set-Cookie": f"admin_session={token}; HttpOnly; SameSite=Lax; Path=/"})
                return

            if path.startswith("/api/admin/"):
                self._require_admin(conn)

            if self.command == "GET" and path == "/api/admin/keys":
                self._send_json({"keys": list_upload_keys(conn)})
                return

            if self.command == "GET" and path == "/api/admin/settings":
                self._send_json({"settings": get_app_settings(conn)})
                return

            if self.command == "POST" and path == "/api/admin/settings":
                payload = self._read_json()
                settings = update_app_settings(
                    conn,
                    public_url=payload.get("publicUrl", ""),
                    default_max_bytes=int(payload.get("defaultMaxBytes") or 100 * 1024 * 1024 * 1024),
                )
                self._send_json({"settings": settings})
                return

            if self.command == "POST" and path == "/api/admin/keys":
                payload = self._read_json()
                if payload.get("plainKey"):
                    key = create_upload_key(
                        conn,
                        label=payload.get("label", ""),
                        plain_key=payload.get("plainKey", ""),
                        max_total_bytes=int(payload.get("maxTotalBytes") or 100 * 1024 * 1024 * 1024),
                        destination_subdir=payload.get("destinationSubdir", ""),
                        allow_folder_upload=bool(payload.get("allowFolderUpload", True)),
                        expires_at=payload.get("expiresAt") or None,
                    )
                    self._send_json({"key": key}, HTTPStatus.CREATED)
                else:
                    link = create_upload_link(
                        conn,
                        label=payload.get("label", ""),
                        max_total_bytes=int(payload.get("maxTotalBytes") or 100 * 1024 * 1024 * 1024),
                        destination_subdir=payload.get("destinationSubdir", ""),
                        allow_folder_upload=bool(payload.get("allowFolderUpload", True)),
                        expires_at=payload.get("expiresAt") or None,
                    )
                    self._send_json({"key": link["record"], "token": link["token"], "uploadUrl": link["upload_url"]}, HTTPStatus.CREATED)
                return

            disable_match = re.fullmatch(r"/api/admin/keys/(\d+)/disable", path)
            if self.command == "POST" and disable_match:
                disable_upload_key(conn, int(disable_match.group(1)))
                self._send_json({"ok": True})
                return

            delete_match = re.fullmatch(r"/api/admin/keys/(\d+)", path)
            if self.command == "DELETE" and delete_match:
                delete_upload_key(conn, int(delete_match.group(1)))
                self._send_json({"ok": True})
                return

            if self.command == "GET" and path == "/api/admin/records":
                self._send_json({"records": list_upload_records(conn)})
                return

            if self.command == "POST" and path == "/api/upload/validate-key":
                payload = self._read_json()
                key = validate_upload_key(conn, payload.get("uploadKey", ""))
                if key is None:
                    raise ApiError(HTTPStatus.UNAUTHORIZED, "Invalid or expired upload key")
                self._send_json({"key": self._public_key(key)})
                return

            if self.command == "POST" and path == "/api/upload/files":
                payload = self._read_json()
                key = self._require_upload_key(conn, payload.get("uploadKey", ""))
                upload_file = create_upload_file(
                    conn,
                    upload_key=key,
                    file_name=payload.get("fileName", ""),
                    relative_path=payload.get("relativePath", "") or payload.get("fileName", ""),
                    size_bytes=int(payload.get("sizeBytes") or 0),
                    chunk_size=int(payload.get("chunkSize") or DEFAULT_CHUNK_SIZE),
                )
                self._send_json({"file": upload_file, "missingChunks": get_missing_chunks(conn, upload_file["id"])}, HTTPStatus.CREATED)
                return

            chunks_match = re.fullmatch(r"/api/upload/files/(\d+)/chunks", path)
            if self.command == "GET" and chunks_match:
                upload_file_id = int(chunks_match.group(1))
                self._require_upload_file_owner(conn, upload_file_id)
                self._send_json({"missingChunks": get_missing_chunks(conn, upload_file_id)})
                return

            chunk_match = re.fullmatch(r"/api/upload/files/(\d+)/chunks/(\d+)", path)
            if self.command == "PUT" and chunk_match:
                upload_file_id = int(chunk_match.group(1))
                self._require_upload_file_owner(conn, upload_file_id)
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                upload_file = receive_chunk(
                    self.config,
                    conn,
                    upload_file_id,
                    int(chunk_match.group(2)),
                    body,
                )
                self._send_json({"file": upload_file, "missingChunks": get_missing_chunks(conn, upload_file["id"])})
                return

            if self.command == "GET" and path == "/api/upload/records":
                key = self._require_upload_key(conn, self.headers.get("X-Upload-Key", ""))
                self._send_json({"records": list_upload_records(conn, key["id"])})
                return

            raise ApiError(HTTPStatus.NOT_FOUND, "Route not found")
        finally:
            conn.close()

    def _require_admin(self, conn):
        token = self._cookies().get("admin_session")
        if not token or get_admin_by_session(conn, token) is None:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Admin login required")

    def _require_upload_key(self, conn, plain_key: str) -> dict:
        key = validate_upload_key(conn, plain_key)
        if key is None:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Invalid or expired upload key")
        return key

    def _require_upload_file_owner(self, conn, upload_file_id: int) -> dict:
        key = self._require_upload_key(conn, self.headers.get("X-Upload-Key", ""))
        upload_file = get_upload_file(conn, upload_file_id)
        if int(upload_file["upload_key_id"]) != int(key["id"]):
            raise ApiError(HTTPStatus.FORBIDDEN, "Upload file does not belong to this key")
        return key

    def _public_key(self, key: dict) -> dict:
        return {
            "id": key["id"],
            "label": key["label"],
            "expiresAt": key["expires_at"],
            "maxTotalBytes": key["max_total_bytes"],
            "destinationSubdir": key["destination_subdir"],
            "allowFolderUpload": bool(key["allow_folder_upload"]),
        }

    def _cookies(self):
        cookies = {}
        header = self.headers.get("Cookie", "")
        for piece in header.split(";"):
            if "=" in piece:
                name, value = piece.strip().split("=", 1)
                cookies[name] = value
        return cookies

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict, status=HTTPStatus.OK, headers=None):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, request_path: str):
        if request_path in ("", "/"):
            request_path = "/index.html"
        relative = request_path.lstrip("/")
        if ".." in Path(relative).parts:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid static path")
        target = STATIC_DIR / relative
        if not target.exists() or not target.is_file():
            target = STATIC_DIR / "index.html"
        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(config: AppConfig):
    FileTransferHandler.config = config
    server = ThreadingHTTPServer((config.host, config.port), FileTransferHandler)
    print(f"Serving file transfer app at http://{config.host}:{config.port}")
    server.serve_forever()


if __name__ == "__main__":
    run(load_config())
