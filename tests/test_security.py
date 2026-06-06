import unittest

from app.security import generate_token, hash_secret, verify_secret


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
