"""Unit tests for secure student account-claim helpers."""
import unittest
from io import BytesIO

from account_services import create_otp, otp_digest, process_profile_photo, verify_otp
from PIL import Image
from types import SimpleNamespace


class ClaimServiceTests(unittest.TestCase):
    def test_otp_is_six_digits(self):
        otp = create_otp()
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

    def test_otp_digest_is_bound_to_challenge(self):
        secret = 'unit-test-secret-that-is-long-enough'
        otp = '123456'
        digest = otp_digest(secret, 41, otp)
        self.assertTrue(verify_otp(secret, 41, otp, digest))
        self.assertFalse(verify_otp(secret, 42, otp, digest))
        self.assertFalse(verify_otp(secret, 41, '123457', digest))

    def test_profile_photo_is_reencoded_and_resized(self):
        source = Image.new('RGB', (1200, 900), (80, 120, 160))
        buffer = BytesIO()
        source.save(buffer, format='PNG')
        upload = SimpleNamespace(stream=BytesIO(buffer.getvalue()))
        result = process_profile_photo(upload)
        with Image.open(BytesIO(result)) as processed:
            self.assertEqual(processed.format, 'JPEG')
            self.assertLessEqual(max(processed.size), 512)
            self.assertEqual(len(processed.getexif()), 0)

    def test_profile_photo_rejects_svg_content(self):
        upload = SimpleNamespace(stream=BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'))
        with self.assertRaises(ValueError):
            process_profile_photo(upload)


if __name__ == '__main__':
    unittest.main()
