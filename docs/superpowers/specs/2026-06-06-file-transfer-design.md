# File Transfer Upload Station Design

## Goal

Build a self-hosted file transfer upload station for a home NAS. Non-technical friends open a browser link, enter an upload key, choose files or a folder, and upload large video materials directly to the NAS.

The first version focuses on receiving files. It is not a full cloud drive, file manager, or public sharing system.

## Target Users

- **Owner/admin:** Runs the application on a NAS with Docker Compose, configures it through a browser, creates upload keys, and reviews upload records.
- **Uploader/friend:** Opens a web page, enters a key, selects files or a folder, watches progress, and sees records for uploads associated with that key/session.

## Deployment Model

The application runs as a Docker Compose service on the NAS. The owner maps NAS folders into the container:

- `/data/uploads` for completed files.
- `/data/config` for app configuration and database.
- `/data/chunks` for temporary upload chunks.

The public entry is recommended to be:

```text
Friend browser
  -> HTTPS domain on VPS
  -> Caddy or Nginx reverse proxy
  -> frps on VPS
  -> frpc on NAS
  -> Docker upload application
  -> NAS storage
```

The VPS runs `frps` and the HTTPS reverse proxy. The NAS runs `frpc` and the Docker application. The NAS management interface is never exposed through FRP.

## First-Run Setup

After Docker Compose starts, the owner opens the local NAS URL and sees an initialization wizard if no admin account exists.

The wizard configures:

- Admin username and password.
- Default completed upload folder.
- Temporary chunk folder.
- Public site URL.
- Default upload limits.

After initialization, normal configuration is done through the web admin UI. The owner should not need to edit application config files for routine use.

## Admin Features

The admin UI supports:

- Create, disable, and delete upload keys.
- Set a key label, such as `Zhang San weekly footage`.
- Set expiration time.
- Set maximum total upload size per key.
- Set destination subfolder per key.
- Enable or disable folder upload per key.
- View all upload records.
- View current active uploads.
- View failed or incomplete uploads.
- Clean stale temporary chunks.

The first version does not include multi-admin roles, public registration, download sharing, file deletion by friends, or a general NAS file browser.

## Uploader Experience

The uploader opens the public URL and sees a simple key entry page:

```text
Enter upload key
[ key input ]
[ continue ]
```

After the key is accepted, the uploader sees:

- Buttons for selecting files and selecting a folder.
- A current upload queue.
- Per-file progress.
- Total progress.
- Upload speed.
- Estimated remaining time.
- Upload status: waiting, uploading, paused, retrying, completed, failed.
- A records section showing uploads visible to this key/session.

Uploader records include:

- File name.
- Relative path when folder upload is used.
- File size.
- Status.
- Completion time.

The uploader cannot browse arbitrary NAS folders, download uploaded files, delete files, or see records from other upload keys.

## Folder Upload

The web app supports browser folder selection where available, primarily Chrome and Edge. The app preserves relative paths from the selected folder.

If a browser does not support folder selection, the UI still supports selecting multiple files.

## Large File Upload Design

Large video uploads use resumable chunked upload, not a single form upload.

Default chunk size: 64 MB.

Upload flow:

1. Browser computes file metadata: name, size, relative path, modified time, and a file identifier.
2. Browser asks the server which chunks already exist.
3. Browser uploads missing chunks.
4. Server stores chunks in a temporary directory scoped by upload key and file identifier.
5. Server records chunk status in the database.
6. When all chunks are present, server verifies the final size and merges chunks.
7. Server moves the completed file to the destination upload folder.
8. Server marks the file record as completed.

If the network disconnects, browser refreshes, or the service restarts, already uploaded chunks remain valid. The uploader can reopen the page, enter the same key, and continue from missing chunks.

## Data Model

Minimum persistent entities:

- `AdminUser`: admin login credentials and setup state.
- `AppSettings`: upload roots, public URL, default limits.
- `UploadKey`: key hash, label, status, expiration, size limit, destination folder, folder-upload permission.
- `UploadFile`: upload key, file name, relative path, size, chunk size, total chunks, status, received bytes, destination path, timestamps.
- `UploadChunk`: upload file ID, chunk index, expected size, received size, status.

The first version uses SQLite because the app is single-node and NAS-hosted.

## Security

Security goals:

- Keep the friend experience simple.
- Do not expose NAS management services.
- Limit damage if an upload key leaks.

Controls:

- Upload keys are stored hashed, not plain text.
- Upload keys can expire and be disabled.
- Each key can have a maximum total upload size.
- Each key writes only under its configured destination folder.
- Relative paths from folder upload are normalized to prevent path traversal.
- File writes are restricted to configured upload and chunk directories.
- Admin UI requires login.
- Public access should go through HTTPS on the VPS.
- Reverse proxy should set conservative request and timeout settings for long uploads.

The first version does not include virus scanning. It can be added later as an optional post-upload hook.

## Error Handling

Expected errors:

- Invalid or expired upload key.
- File exceeds key or server limit.
- Insufficient NAS disk space.
- Chunk upload timeout.
- Chunk size mismatch.
- Merge failure.
- Browser folder upload unsupported.

The uploader UI should show plain-language status and retry options. Failed chunks should retry automatically a limited number of times. Failed files should remain visible in the records list and support retry when possible.

The admin UI should show failed uploads and stale temporary data so the owner can clean them.

## Observability

The app should provide:

- Admin upload records.
- Active upload status.
- Failed upload status.
- Basic container logs.

First version does not need Prometheus, external logging, or alerting.

## Testing Strategy

Core tests:

- Upload key validation.
- Path normalization and traversal prevention.
- Chunk status query.
- Chunk upload and resume.
- File merge correctness.
- Expired key and disabled key rejection.
- Upload size limit enforcement.

Manual verification:

- Start with Docker Compose.
- Complete first-run setup in the browser.
- Create an upload key.
- Upload multiple small files.
- Upload a folder and verify relative paths.
- Simulate interrupted upload and resume.
- Upload a large test file.
- Confirm files land in the mapped NAS upload directory.

## Out of Scope For Version 1

- Friend accounts and registration.
- Friend downloads.
- General NAS file browsing.
- File preview or video playback.
- Public file sharing links.
- Multi-admin permission roles.
- Mobile app.
- Virus scanning.
- Built-in FRP management UI.

## Recommended First Implementation Shape

Use a single Docker image containing:

- Backend API.
- Static frontend assets.
- SQLite database.
- Local filesystem storage.

The Compose file should require only port and volume mappings for normal use. Routine application settings should be changed from the admin web UI after startup.

Suggested default app port: `8080`.

Example Compose shape:

```yaml
services:
  file-transfer:
    image: file-transfer:latest
    ports:
      - "8080:8080"
    volumes:
      - /path/on/nas/uploads:/data/uploads
      - /path/on/nas/config:/data/config
      - /path/on/nas/chunks:/data/chunks
```

## Deployment Notes

FRP itself should be configured outside this application:

- VPS: `frps`.
- NAS: `frpc`.
- VPS reverse proxy: Caddy or Nginx with HTTPS.

The app documentation should include sample FRP and reverse proxy configs, but the upload app should not depend on managing FRP directly.
