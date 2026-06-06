import unittest

from app.storage import merge_chunks, normalize_relative_path, write_chunk


class StorageTest(unittest.TestCase):
    def test_normalize_relative_path_blocks_traversal(self):
        with self.assertRaises(ValueError):
            normalize_relative_path("../secret.mov")
        with self.assertRaises(ValueError):
            normalize_relative_path("/absolute.mov")
        self.assertEqual(normalize_relative_path("day1/cam.mov"), "day1/cam.mov")

    def test_merge_chunks_writes_destination_in_order(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunks = root / "chunks"
            destination = root / "uploads" / "clip.txt"
            write_chunk(chunks, 1, 2, 1, b"world")
            write_chunk(chunks, 1, 2, 0, b"hello ")

            written = merge_chunks(chunks, 1, 2, 2, destination)

            self.assertEqual(written, 11)
            self.assertEqual(destination.read_bytes(), b"hello world")
