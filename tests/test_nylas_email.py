"""Tests for the Nylas Transactional Send integration without network calls."""
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from account_services import (
    EmailDeliveryError,
    email_delivery_is_configured,
    send_transactional_email,
)


class FakeResponse:
    status = 200

    def __init__(self, payload=None):
        self.payload = json.dumps(payload or {"data": {"message_id": "test-message"}}).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit=-1):
        return self.payload[:limit]


BASE_ENV = {
    "NYLAS_API_KEY": "test-nylas-key",
    "NYLAS_DOMAIN": "studentverifi-test.nylas.email",
    "NYLAS_FROM_EMAIL": "no-reply@studentverifi-test.nylas.email",
    "NYLAS_FROM_NAME": "StudentVerifi",
    "NYLAS_API_BASE_URL": "https://api.us.nylas.com",
    "NYLAS_REPLY_TO": "support@example.org",
}


class NylasEmailTests(unittest.TestCase):
    def test_transactional_send_uses_verified_domain_endpoint_and_payload(self):
        with patch.dict(os.environ, BASE_ENV, clear=True):
            with patch("account_services.urllib.request.urlopen", return_value=FakeResponse()) as send:
                result = send_transactional_email(
                    "student@example.org",
                    "Your verification code",
                    "<p>Your code is <strong>123456</strong>.</p>",
                    "student-claim-42",
                )

        request = send.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://api.us.nylas.com/v3/domains/studentverifi-test.nylas.email/messages/send",
        )
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-nylas-key")
        self.assertEqual(request.get_header("Idempotency-key"), "student-claim-42")
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["to"], [{"email": "student@example.org"}])
        self.assertEqual(payload["from"], {
            "name": "StudentVerifi",
            "email": "no-reply@studentverifi-test.nylas.email",
        })
        self.assertEqual(payload["body"], "<p>Your code is <strong>123456</strong>.</p>")
        self.assertFalse(payload["is_plaintext"])
        self.assertEqual(payload["reply_to"], [{"email": "support@example.org"}])
        self.assertEqual(result["data"]["message_id"], "test-message")

    def test_european_region_is_supported(self):
        env = dict(BASE_ENV, NYLAS_API_BASE_URL="https://api.eu.nylas.com")
        with patch.dict(os.environ, env, clear=True):
            with patch("account_services.urllib.request.urlopen", return_value=FakeResponse()) as send:
                send_transactional_email("student@example.org", "Subject", "<p>Body</p>")
        self.assertTrue(send.call_args.args[0].full_url.startswith("https://api.eu.nylas.com/"))

    def test_missing_configuration_is_reported_without_network_call(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(email_delivery_is_configured())
            with self.assertRaises(EmailDeliveryError):
                send_transactional_email("student@example.org", "Subject", "<p>Body</p>")

    def test_sender_must_match_verified_domain(self):
        env = dict(BASE_ENV, NYLAS_FROM_EMAIL="no-reply@another.example")
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(email_delivery_is_configured())
            with self.assertRaisesRegex(EmailDeliveryError, "verified sending domain"):
                send_transactional_email("student@example.org", "Subject", "<p>Body</p>")

    def test_api_base_url_is_limited_to_official_regional_hosts(self):
        env = dict(BASE_ENV, NYLAS_API_BASE_URL="https://attacker.example")
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(EmailDeliveryError, "region configuration"):
                send_transactional_email("student@example.org", "Subject", "<p>Body</p>")

    def test_provider_http_error_does_not_expose_response_body(self):
        env = dict(BASE_ENV)
        error = HTTPError(
            "https://api.us.nylas.com/test", 401, "Unauthorized", {}, None
        )
        with patch.dict(os.environ, env, clear=True):
            with patch("account_services.urllib.request.urlopen", side_effect=error):
                with self.assertRaisesRegex(EmailDeliveryError, "Nylas returned HTTP 401"):
                    send_transactional_email("student@example.org", "Subject", "<p>Body</p>")


if __name__ == "__main__":
    unittest.main()
