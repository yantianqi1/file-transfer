import tempfile
import unittest
from pathlib import Path

from app.config import AppConfig
from app.db import connect, initialize
from app.services import (
    complete_setup,
    create_upload_file,
    create_upload_key,
    create_upload_link,
    get_admin_by_session,
    get_app_settings,
    get_missing_chunks,
    is_initialized,
    login_admin,
    receive_chunk,
    update_app_settings,
    validate_upload_key,
)


class ServicesTest(unittest.TestCase):
    def make_context(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        config = AppConfig(
            uploads_dir=root / "uploads",
            config_dir=root / "config",
            chunks_dir=root / "chunks",
            host="127.0.0.1",
            port=0,
        )
        conn = connect(config)
        initialize(conn)
        self.addCleanup(temp.cleanup)
        return config, conn

    def test_new_database_is_not_initialized(self):
        _config, conn = self.make_context()
        self.assertFalse(is_initialized(conn))

    def test_complete_setup_creates_admin_and_settings(self):
        config, conn = self.make_context()
        complete_setup(
            conn,
            username="admin",
            password="secret-pass",
            uploads_dir=config.uploads_dir,
            chunks_dir=config.chunks_dir,
            public_url="https://files.example.test",
            default_max_bytes=1024,
        )

        self.assertTrue(is_initialized(conn))
        token = login_admin(conn, "admin", "secret-pass")
        self.assertIsNotNone(token)
        self.assertEqual(get_admin_by_session(conn, token)["username"], "admin")
        self.assertIsNone(login_admin(conn, "admin", "wrong"))

    def test_settings_can_be_updated_from_admin_ui(self):
        config, conn = self.make_context()
        complete_setup(
            conn,
            username="admin",
            password="secret-pass",
            uploads_dir=config.uploads_dir,
            chunks_dir=config.chunks_dir,
            public_url="",
            default_max_bytes=1024,
        )

        settings = update_app_settings(
            conn,
            public_url="https://upload.example.com/",
            default_max_bytes=2048,
        )

        self.assertEqual(settings["public_url"], "https://upload.example.com")
        self.assertEqual(settings["default_max_bytes"], 2048)
        self.assertEqual(get_app_settings(conn)["public_url"], "https://upload.example.com")

    def test_upload_key_can_be_created_validated_and_disabled(self):
        config, conn = self.make_context()
        complete_setup(
            conn,
            username="admin",
            password="secret-pass",
            uploads_dir=config.uploads_dir,
            chunks_dir=config.chunks_dir,
            public_url="",
            default_max_bytes=2048,
        )

        key = create_upload_key(
            conn,
            label="weekly footage",
            plain_key="friend-key",
            max_total_bytes=2048,
            destination_subdir="project-a",
            allow_folder_upload=True,
            expires_at=None,
        )

        validated = validate_upload_key(conn, "friend-key")
        self.assertEqual(validated["id"], key["id"])
        self.assertEqual(validated["destination_subdir"], "project-a")

        conn.execute("UPDATE upload_keys SET status = 'disabled' WHERE id = ?", (key["id"],))
        conn.commit()
        self.assertIsNone(validate_upload_key(conn, "friend-key"))

    def test_create_upload_link_returns_copyable_public_url_once(self):
        config, conn = self.make_context()
        complete_setup(
            conn,
            username="admin",
            password="secret-pass",
            uploads_dir=config.uploads_dir,
            chunks_dir=config.chunks_dir,
            public_url="https://upload.example.com",
            default_max_bytes=2048,
        )

        link = create_upload_link(
            conn,
            label="client footage",
            max_total_bytes=2048,
            destination_subdir="client-a",
            allow_folder_upload=True,
            expires_at=None,
        )

        self.assertEqual(link["upload_url"], f"https://upload.example.com/u/{link['token']}")
        self.assertEqual(link["record"]["label"], "client footage")
        self.assertNotIn(link["token"], link["record"].get("key_hash", ""))
        self.assertEqual(validate_upload_key(conn, link["token"])["id"], link["record"]["id"])

    def test_receive_chunks_merges_file_when_complete(self):
        config, conn = self.make_context()
        complete_setup(
            conn,
            username="admin",
            password="secret-pass",
            uploads_dir=config.uploads_dir,
            chunks_dir=config.chunks_dir,
            public_url="",
            default_max_bytes=100,
        )
        key = create_upload_key(
            conn,
            label="camera",
            plain_key="friend-key",
            max_total_bytes=100,
            destination_subdir="shoot",
            allow_folder_upload=True,
            expires_at=None,
        )
        upload_file = create_upload_file(
            conn,
            upload_key=key,
            file_name="clip.txt",
            relative_path="day1/clip.txt",
            size_bytes=11,
            chunk_size=6,
        )

        self.assertEqual(get_missing_chunks(conn, upload_file["id"]), [0, 1])
        receive_chunk(config, conn, upload_file["id"], 1, b"world")
        self.assertEqual(get_missing_chunks(conn, upload_file["id"]), [0])
        result = receive_chunk(config, conn, upload_file["id"], 0, b"hello ")

        self.assertEqual(result["status"], "completed")
        completed = config.uploads_dir / "shoot" / "day1" / "clip.txt"
        self.assertEqual(completed.read_text(), "hello world")

    def test_create_upload_file_rejects_key_size_limit(self):
        config, conn = self.make_context()
        complete_setup(
            conn,
            username="admin",
            password="secret-pass",
            uploads_dir=config.uploads_dir,
            chunks_dir=config.chunks_dir,
            public_url="",
            default_max_bytes=5,
        )
        key = create_upload_key(
            conn,
            label="small",
            plain_key="small-key",
            max_total_bytes=5,
            destination_subdir="",
            allow_folder_upload=True,
            expires_at=None,
        )

        with self.assertRaises(ValueError):
            create_upload_file(
                conn,
                upload_key=key,
                file_name="too-big.txt",
                relative_path="too-big.txt",
                size_bytes=6,
                chunk_size=6,
            )
