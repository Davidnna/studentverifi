"""Verify the actual installed dependency rather than the mocked SDK.

No credentials or Blob network calls are needed. Required in GitHub Actions.
"""
import asyncio
import inspect
import unittest
from importlib.metadata import version


class InstalledBlobSDKTests(unittest.TestCase):
    def test_installed_sdk_supports_private_photo_upload_metadata_and_delete(self):
        from vercel.blob import AsyncBlobClient

        self.assertEqual(version("vercel"), "0.5.7")
        inspect.signature(AsyncBlobClient).bind(token="test-token-not-used")

        async def check():
            client = AsyncBlobClient(token="vercel_blob_rw_test_not_a_real_secret")
            try:
                inspect.signature(client.put).bind(
                    "student-profiles/17/test.jpg", b"image", access="private",
                    content_type="image/jpeg", add_random_suffix=True,
                )
                inspect.signature(client.head).bind("student-profiles/17/test.jpg")
                inspect.signature(client.delete).bind(["student-profiles/17/test.jpg"])
                self.assertTrue(inspect.iscoroutinefunction(client.put))
                self.assertTrue(inspect.iscoroutinefunction(client.head))
                self.assertTrue(inspect.iscoroutinefunction(client.delete))
            finally:
                await client.aclose()

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
