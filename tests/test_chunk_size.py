import unittest
from pathlib import Path

from app.server import DEFAULT_CHUNK_SIZE


class ChunkSizeTest(unittest.TestCase):
    def test_default_chunk_size_is_proxy_friendly(self):
        expected = 8 * 1024 * 1024

        self.assertEqual(DEFAULT_CHUNK_SIZE, expected)
        static_js = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.js").read_text()
        self.assertIn("const CHUNK_SIZE = 8 * 1024 * 1024;", static_js)
