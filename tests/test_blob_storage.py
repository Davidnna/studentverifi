"""Private Vercel Blob integration tests using an isolated SDK stub."""
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from account_services import (
    PhotoStorageError,
    delete_private_profile_photo,
    read_private_profile_photo,
    upload_private_profile_photo,
)


class FakeBlobClient:
    uploaded_path = None
    deleted_paths = None
    stored_bytes = b"student-photo-bytes"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def put(self, pathname, body, **options):
        self.__class__.uploaded_path = pathname
        self.__class__.upload_options = options
        self.__class__.stored_bytes = body
        return SimpleNamespace(pathname=pathname)

    async def get(self, pathname, **options):
        self.__class__.get_options = options

        async def stream():
            yield self.__class__.stored_bytes

        return SimpleNamespace(status_code=200, stream=stream())

    async def delete(self, paths):
        self.__class__.deleted_paths = paths


class PrivateBlobTests(unittest.TestCase):
    def setUp(self):
        FakeBlobClient.uploaded_path = None
        FakeBlobClient.deleted_paths = None
        FakeBlobClient.stored_bytes = b"student-photo-bytes"
        self.blob_module = types.ModuleType("vercel.blob")
        self.blob_module.AsyncBlobClient = FakeBlobClient
        self.vercel_module = types.ModuleType("vercel")
        self.vercel_module.blob = self.blob_module
        self.modules = patch.dict(sys.modules, {
            "vercel": self.vercel_module,
            "vercel.blob": self.blob_module,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_upload_uses_private_access_and_randomised_student_path(self):
        pathname = upload_private_profile_photo(17, b"processed-jpeg")
        self.assertEqual(pathname, FakeBlobClient.uploaded_path)
        self.assertTrue(pathname.startswith("student-profiles/17/"))
        self.assertEqual(FakeBlobClient.upload_options["access"], "private")
        self.assertEqual(FakeBlobClient.upload_options["content_type"], "image/jpeg")
        self.assertTrue(FakeBlobClient.upload_options["add_random_suffix"])

    def test_private_photo_retrieval_uses_private_access(self):
        result = read_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertEqual(result, b"student-photo-bytes")
        self.assertEqual(FakeBlobClient.get_options["access"], "private")

    def test_delete_only_accepts_student_profile_paths(self):
        delete_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertEqual(FakeBlobClient.deleted_paths, ["student-profiles/17/photo.jpg"])
        delete_private_profile_photo("other-folder/photo.jpg")
        self.assertEqual(FakeBlobClient.deleted_paths, ["student-profiles/17/photo.jpg"])

    def test_photo_read_rejects_paths_outside_student_folder(self):
        with self.assertRaises(PhotoStorageError):
            read_private_profile_photo("public/photo.jpg")


if __name__ == "__main__":
    unittest.main()
