# File Transfer MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Docker-ready NAS file transfer upload station with first-run admin setup, upload keys, resumable chunk uploads, SQLite persistence, and simple admin/uploader web screens.

**Architecture:** A single Python standard-library HTTP server serves static frontend files and JSON APIs. SQLite stores setup state, admin sessions, upload keys, file records, and chunk records. Files are written only under configured upload and chunk roots.

**Tech Stack:** Python 3.12 standard library, SQLite, vanilla HTML/CSS/JavaScript, Docker Compose, `unittest`.

---

## File Structure

- `app/server.py`: HTTP entrypoint, routing, request parsing, static file serving.
- `app/config.py`: Environment-driven path and server configuration.
- `app/db.py`: SQLite connection, schema creation, transaction helper.
- `app/security.py`: Password hashing, upload key hashing, token generation, constant-time comparisons.
- `app/storage.py`: Path normalization, chunk paths, merge logic, stale chunk cleanup.
- `app/services.py`: Application operations for setup, auth, upload keys, upload records, chunks.
- `app/static/index.html`: Single-page application shell.
- `app/static/styles.css`: Responsive application styles.
- `app/static/app.js`: Admin and uploader UI behavior.
- `tests/test_security.py`: Security helper tests.
- `tests/test_storage.py`: Path and merge tests.
- `tests/test_services.py`: SQLite service behavior tests.
- `Dockerfile`: Production image.
- `docker-compose.yml`: NAS-friendly example service.
- `README.md`: Local and Docker usage notes.

## Task 1: Project Skeleton And Database

**Files:**
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/db.py`
- Create: `tests/test_services.py`

- [ ] **Step 1: Write failing database setup test**

```python
import tempfile
import unittest
from pathlib import Path

from app.config import AppConfig
from app.db import connect, initialize
from app.services import is_initialized


class ServicesTest(unittest.TestCase):
    def test_new_database_is_not_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                uploads_dir=root / "uploads",
                config_dir=root / "config",
                chunks_dir=root / "chunks",
                host="127.0.0.1",
                port=0,
            )
            conn = connect(config)
            initialize(conn)
            self.assertFalse(is_initialized(conn))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_services -v`
Expected: FAIL with missing `app` modules or missing `is_initialized`.

- [ ] **Step 3: Implement config, SQLite schema, and initialization check**

Create `app/config.py`, `app/db.py`, `app/services.py`, and `app/__init__.py` with database tables for admin users, settings, sessions, upload keys, upload files, and upload chunks. `is_initialized(conn)` returns true only when an admin user exists.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_services -v`
Expected: PASS.

## Task 2: Security And Path Safety

**Files:**
- Create: `app/security.py`
- Create: `app/storage.py`
- Create: `tests/test_security.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing security and storage tests**

```python
import unittest

from app.security import hash_secret, verify_secret, generate_token
from app.storage import normalize_relative_path


class SecurityTest(unittest.TestCase):
    def test_secret_hash_verifies_without_storing_plain_text(self):
        digest = hash_secret("correct horse")
        self.assertNotIn("correct horse", digest)
        self.assertTrue(verify_secret("correct horse", digest))
        self.assertFalse(verify_secret("wrong", digest))

    def test_generated_tokens_are_url_safe(self):
        token = generate_token(24)
        self.assertGreaterEqual(len(token), 24)
        self.assertNotIn("/", token)
```

```python
import unittest

from app.storage import normalize_relative_path


class StorageTest(unittest.TestCase):
    def test_normalize_relative_path_blocks_traversal(self):
        with self.assertRaises(ValueError):
            normalize_relative_path("../secret.mov")
        with self.assertRaises(ValueError):
            normalize_relative_path("/absolute.mov")
        self.assertEqual(normalize_relative_path("day1/cam.mov"), "day1/cam.mov")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_security tests.test_storage -v`
Expected: FAIL with missing modules or functions.

- [ ] **Step 3: Implement PBKDF2 hashing, token generation, and relative path normalization**

Use `hashlib.pbkdf2_hmac`, `secrets.token_urlsafe`, `hmac.compare_digest`, `posixpath.normpath`, and reject absolute paths, empty paths, `..`, and traversal segments.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_security tests.test_storage -v`
Expected: PASS.

## Task 3: Setup, Login, And Upload Keys

**Files:**
- Modify: `app/services.py`
- Modify: `tests/test_services.py`

- [ ] **Step 1: Add failing service tests**

Test that `complete_setup` creates the admin and settings, `login_admin` returns a session token for valid credentials only, `create_upload_key` stores a hashed key, and disabled keys fail validation.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m unittest tests.test_services -v`
Expected: FAIL with missing service functions.

- [ ] **Step 3: Implement setup, admin session, upload key CRUD, and key validation**

Add service functions: `complete_setup`, `login_admin`, `get_admin_by_session`, `create_upload_key`, `list_upload_keys`, `disable_upload_key`, `delete_upload_key`, and `validate_upload_key`.

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m unittest tests.test_services -v`
Expected: PASS.

## Task 4: Chunked Upload Core

**Files:**
- Modify: `app/storage.py`
- Modify: `app/services.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_services.py`

- [ ] **Step 1: Add failing chunk tests**

Test creating an upload file, querying missing chunks, writing chunks out of order, merging once all chunks exist, preserving folder relative paths, and rejecting uploads over a key size limit.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m unittest tests.test_storage tests.test_services -v`
Expected: FAIL with missing chunk helpers and services.

- [ ] **Step 3: Implement chunk registration, chunk writes, merge, status updates, and size accounting**

Use chunk files under `<chunks>/<upload_key_id>/<file_id>/<index>.part`. Merge in index order into the key destination under uploads, creating parent folders only after normalized relative paths pass validation.

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m unittest tests.test_storage tests.test_services -v`
Expected: PASS.

## Task 5: HTTP API And Static App

**Files:**
- Create: `app/server.py`
- Create: `app/static/index.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`

- [ ] **Step 1: Add API routes**

Implement `GET /api/setup/status`, `POST /api/setup`, `POST /api/admin/login`, `GET /api/admin/keys`, `POST /api/admin/keys`, `POST /api/admin/keys/<id>/disable`, `DELETE /api/admin/keys/<id>`, `POST /api/upload/validate-key`, `POST /api/upload/files`, `GET /api/upload/files/<id>/chunks`, `PUT /api/upload/files/<id>/chunks/<index>`, and `GET /api/upload/records`.

- [ ] **Step 2: Add frontend screens**

Create a single static page that switches between first-run setup, admin login, admin dashboard, upload key entry, and uploader queue. Include file selection, folder selection where supported, progress bars, speed, retry status, and upload records.

- [ ] **Step 3: Run the server locally**

Run: `python3 -m app.server`
Expected: server listens on `http://127.0.0.1:8080` unless `PORT` is set.

## Task 6: Docker And Documentation

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `README.md`

- [ ] **Step 1: Add Docker packaging**

Use `python:3.12-slim`, copy the app, expose `8080`, set `/data/uploads`, `/data/config`, and `/data/chunks` as defaults.

- [ ] **Step 2: Add NAS usage documentation**

Document local run, Docker Compose run, volume mapping, first-run setup, upload key creation, and FRP/Caddy placement as external infrastructure.

- [ ] **Step 3: Run verification**

Run: `python3 -m unittest discover -v`
Expected: PASS.

Run: `python3 -m app.server`
Expected: server starts and serves the app.

## Self-Review

- Spec coverage: first-run setup, admin login, upload keys, folder upload, resumable chunks, SQLite, path safety, Docker Compose, and manual verification are covered.
- Deferred from version 1 per spec: friend accounts, downloads, NAS file browsing, preview/playback, public sharing, multi-admin roles, mobile app, virus scanning, and FRP management UI.
- Placeholder scan: no unresolved implementation placeholders are required for the first MVP.
- Type consistency: service and storage function names are introduced before HTTP usage.
