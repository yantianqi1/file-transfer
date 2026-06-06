import unittest
from pathlib import Path


class FrontendUploadProgressTest(unittest.TestCase):
    def test_chunk_upload_reports_live_progress_and_speed(self):
        app_js = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.js").read_text()

        self.assertIn("function uploadChunkWithProgress", app_js)
        self.assertIn("new XMLHttpRequest()", app_js)
        self.assertIn("xhr.upload.onprogress", app_js)
        self.assertIn("onProgress", app_js)
