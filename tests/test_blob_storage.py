"""Private Vercel Blob integration tests using an isolated SDK stub."""
import os
import sys
import types
import urllib.error
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
    head_url = "https://twrnsww5pe4g7xyp.private.blob.vercel-storage.com/student-profiles/17/photo.jpg"

    def __init__(self, *, token):
        self.__class__.client_token = token

    async def aclose(self):
        self.__class__.closed = True

    async def put(self, pathname, body, *, access, content_type, add_random_suffix):
        self.__class__.uploaded_path = pathname
        self.__class__.upload_options = dict(access=access, content_type=content_type, add_random_suffix=add_random_suffix)
        self.__class__.stored_bytes = body
        return SimpleNamespace(pathname=pathname)

    async def head(self, pathname):
        self.__class__.head_path = pathname
        if self.__class__.head_url is None:
            return None
        return SimpleNamespace(url=self.__class__.head_url)

    async def delete(self, paths):
        self.__class__.deleted_paths = paths


class PrivateBlobTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_twrnsww5pe4g7xyp_test-secret"})
        self.env.start()
        self.addCleanup(self.env.stop)
        FakeBlobClient.closed = False
        FakeBlobClient.uploaded_path = None
        FakeBlobClient.deleted_paths = None
        FakeBlobClient.stored_bytes = b"student-photo-bytes"
        FakeBlobClient.head_url = "https://twrnsww5pe4g7xyp.private.blob.vercel-storage.com/student-profiles/17/photo.jpg"
        FakeBlobClient.head_path = None
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
        self.assertEqual(FakeBlobClient.client_token, "vercel_blob_rw_twrnsww5pe4g7xyp_test-secret")
        self.assertTrue(FakeBlobClient.closed)

    def test_private_photo_retrieval_uses_authenticated_store_url(self):
        image = b"\xff\xd8\xff" + b"processed-jpeg"

        class Response:
            status = 200
            headers = {"Content-Type": "image/jpeg"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, limit):
                self.limit = limit
                return image

        # A nonstandard but SDK-accepted token must not be rejected by our own parser.
        with patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "opaque-sdk-credential"}):
            with patch("account_services.urllib.request.urlopen", return_value=Response()) as download:
                result = read_private_profile_photo("student-profiles/17/photo.jpg")

        self.assertEqual(result, image)
        self.assertEqual(FakeBlobClient.head_path, "student-profiles/17/photo.jpg")
        self.assertEqual(FakeBlobClient.client_token, "opaque-sdk-credential")
        self.assertTrue(FakeBlobClient.closed)
        request = download.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://twrnsww5pe4g7xyp.private.blob.vercel-storage.com/student-profiles/17/photo.jpg",
        )
        self.assertEqual(request.get_header("Authorization"),
                         "Bearer opaque-sdk-credential")
        self.assertEqual(request.get_header("Accept"), "image/jpeg")
        self.assertEqual(download.call_args.kwargs["timeout"], 15)

    def test_private_photo_retrieval_handles_not_found(self):
        error = urllib.error.HTTPError("https://blob.invalid/photo.jpg", 404, "Not Found", {}, None)
        with patch("account_services.urllib.request.urlopen", side_effect=error):
            self.assertIsNone(read_private_profile_photo("student-profiles/17/photo.jpg"))

    def test_private_photo_retrieval_rejects_access_denied(self):
        error = urllib.error.HTTPError("https://blob.invalid/photo.jpg", 403, "Forbidden", {}, None)
        with patch("account_services.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(PhotoStorageError) as caught:
                read_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertEqual(caught.exception.reason, "blob_access_denied")

    def test_private_photo_retrieval_rejects_invalid_jpeg(self):
        class Response:
            status = 200
            headers = {"Content-Type": "image/jpeg"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return b"not-an-image"

        with patch("account_services.urllib.request.urlopen", return_value=Response()):
            with self.assertRaises(PhotoStorageError) as caught:
                read_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertEqual(caught.exception.reason, "blob_invalid_response")

    def test_private_photo_retrieval_enforces_maximum_size(self):
        class Response:
            status = 200
            headers = {"Content-Type": "image/jpeg"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return b"\xff\xd8\xff" + (b"x" * limit)

        with patch("account_services.urllib.request.urlopen", return_value=Response()):
            with self.assertRaises(PhotoStorageError) as caught:
                read_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertEqual(caught.exception.reason, "blob_invalid_response")

    def test_private_photo_retrieval_does_not_parse_token_format(self):
        with patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "opaque-sdk-credential"}):
            with patch("account_services.urllib.request.urlopen") as download:
                class Response:
                    status = 200
                    headers = {"Content-Type": "image/jpeg"}
                    def __enter__(self): return self
                    def __exit__(self, *args): return False
                    def read(self, limit): return b"\xff\xd8\xffphoto"
                download.return_value = Response()
                image = read_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertTrue(image.startswith(b"\xff\xd8\xff"))

    def test_private_photo_retrieval_rejects_untrusted_metadata_url(self):
        FakeBlobClient.head_url = "https://attacker.example/student-profiles/17/photo.jpg"
        with self.assertRaises(PhotoStorageError) as caught:
            read_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertEqual(caught.exception.reason, "blob_metadata_invalid")

    def test_private_photo_retrieval_rejects_metadata_path_mismatch(self):
        FakeBlobClient.head_url = "https://twrnsww5pe4g7xyp.private.blob.vercel-storage.com/student-profiles/18/photo.jpg"
        with self.assertRaises(PhotoStorageError) as caught:
            read_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertEqual(caught.exception.reason, "blob_metadata_invalid")

    def test_private_photo_retrieval_handles_missing_metadata(self):
        FakeBlobClient.head_url = None
        with patch("account_services.urllib.request.urlopen") as download:
            self.assertIsNone(read_private_profile_photo("student-profiles/17/photo.jpg"))
        download.assert_not_called()

    def test_delete_only_accepts_student_profile_paths(self):
        delete_private_profile_photo("student-profiles/17/photo.jpg")
        self.assertEqual(FakeBlobClient.deleted_paths, ["student-profiles/17/photo.jpg"])
        delete_private_profile_photo("other-folder/photo.jpg")
        self.assertEqual(FakeBlobClient.deleted_paths, ["student-profiles/17/photo.jpg"])

    def test_missing_token_has_safe_diagnostic(self):
        with patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": ""}):
            with self.assertRaises(PhotoStorageError) as caught:
                upload_private_profile_photo(17, b"photo")
        self.assertEqual(caught.exception.reason, "missing_blob_token")
        self.assertIsNone(FakeBlobClient.uploaded_path)

    def test_provider_error_does_not_log_secret_or_exception_message(self):
        with patch.object(FakeBlobClient, "put", side_effect=TypeError("SECRET example")):
            with self.assertLogs("account_services", level="WARNING") as logs:
                with self.assertRaises(PhotoStorageError) as caught:
                    upload_private_profile_photo(17, b"photo")
        self.assertEqual(caught.exception.reason, "blob_sdk_incompatible")
        self.assertNotIn("SECRET", str(caught.exception) + str(logs.output))

    def test_photo_read_rejects_paths_outside_student_folder(self):
        with self.assertRaises(PhotoStorageError):
            read_private_profile_photo("public/photo.jpg")
        with self.assertRaises(PhotoStorageError):
            read_private_profile_photo("student-profiles/17/../../private.jpg")


if __name__ == "__main__":
    unittest.main()
