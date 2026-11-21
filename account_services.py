"""Account-claim, email-delivery and private profile-photo services."""
import asyncio
import hashlib
import html
import hmac
import json
import os
import secrets
import urllib.error
import urllib.request
from io import BytesIO


MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PROFILE_PHOTO_PIXELS = 20_000_000
OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60
OTP_MAX_SENDS_PER_HOUR = 5
CLAIM_COMPLETION_TTL_MINUTES = 20


class EmailDeliveryError(RuntimeError):
    """Raised when the configured transactional email provider rejects a send."""


class PhotoStorageError(RuntimeError):
    """Raised when private profile-photo storage is unavailable."""


def create_otp():
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def otp_digest(secret_key, challenge_id, otp):
    message = f"student-claim:{challenge_id}:{otp}".encode("utf-8")
    return hmac.new(str(secret_key).encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_otp(secret_key, challenge_id, otp, expected_digest):
    if not expected_digest or not str(otp).isdigit() or len(str(otp)) != OTP_LENGTH:
        return False
    supplied = otp_digest(secret_key, challenge_id, str(otp))
    return hmac.compare_digest(supplied, str(expected_digest))


def send_transactional_email(to_address, subject, text_body, html_body, idempotency_key=None):
    """Send a transactional email through Resend's HTTPS API."""
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    sender = (os.environ.get("MAIL_FROM") or "").strip()
    if not api_key or not sender:
        raise EmailDeliveryError("Transactional email is not configured.")

    payload = json.dumps({
        "from": sender,
        "to": [to_address],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = str(idempotency_key)[:256]

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status < 200 or response.status >= 300:
                raise EmailDeliveryError("The email provider rejected the message.")
            response.read(4096)
    except urllib.error.HTTPError as error:
        # Do not expose provider response bodies, recipient addresses or secrets.
        raise EmailDeliveryError(f"Email provider returned HTTP {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise EmailDeliveryError("The email provider could not be reached.") from error


def send_claim_otp(to_address, otp, challenge_id, institution_name="StudentVerifi"):
    safe_name = html.escape(institution_name or "StudentVerifi")
    subject = f"Your {institution_name} account verification code"
    text_body = (
        f"Your StudentVerifi account-claim code is {otp}. "
        f"It expires in {OTP_TTL_MINUTES} minutes. If you did not request it, ignore this email."
    )
    html_body = (
        "<div style=\"font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#172033\">"
        f"<p style=\"font-size:13px;letter-spacing:1px;color:#52627a\">{safe_name}</p>"
        "<h2>Verify your student account</h2>"
        "<p>Use the one-time code below to continue claiming your student account.</p>"
        f"<p style=\"font-size:30px;font-weight:700;letter-spacing:8px;padding:16px;background:#f3f6fb;border-radius:12px;text-align:center\">{otp}</p>"
        f"<p>This code expires in {OTP_TTL_MINUTES} minutes and can only be used once.</p>"
        "<p>If you did not request this code, you can ignore this message.</p>"
        "</div>"
    )
    send_transactional_email(
        to_address,
        subject,
        text_body,
        html_body,
        idempotency_key=f"student-claim-otp/{challenge_id}",
    )


def send_verifier_invitation(to_address, display_name, invitation_url, invitation_id):
    safe_name = html.escape(display_name or "colleague")
    safe_url = html.escape(invitation_url, quote=True)
    text_body = (
        "You have been invited to verify student credentials through StudentVerifi. "
        f"Accept your invitation here: {invitation_url}. The link expires in 48 hours."
    )
    html_body = (
        "<div style=\"font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#172033\">"
        f"<h2>Hello {safe_name},</h2>"
        "<p>You have been invited to use StudentVerifi as an authorised verifier.</p>"
        f"<p><a href=\"{safe_url}\">Accept invitation and create your password</a></p>"
        "<p>This invitation expires in 48 hours. If you were not expecting it, ignore this email.</p>"
        "</div>"
    )
    send_transactional_email(
        to_address,
        "Your StudentVerifi verifier invitation",
        text_body,
        html_body,
        idempotency_key=f"verifier-invitation/{invitation_id}",
    )


def process_profile_photo(file_storage):
    """Validate and re-encode a portrait image, removing EXIF and metadata."""
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as error:
        raise PhotoStorageError("Image processing is not available on this deployment.") from error

    raw = file_storage.stream.read(MAX_PROFILE_PHOTO_BYTES + 1)
    if not raw:
        raise ValueError("Choose a profile photograph before continuing.")
    if len(raw) > MAX_PROFILE_PHOTO_BYTES:
        raise ValueError("The profile photograph must not exceed 2 MB.")

    try:
        with Image.open(BytesIO(raw)) as probe:
            if probe.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Use a JPEG, PNG or WebP profile photograph.")
            if probe.width * probe.height > MAX_PROFILE_PHOTO_PIXELS:
                raise ValueError("The photograph dimensions are too large.")
            probe.verify()
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            if image.width < 120 or image.height < 120:
                raise ValueError("Use a clear photograph at least 120 pixels wide and high.")
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="JPEG", quality=86, optimize=True, progressive=True)
            result = output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("The uploaded file is not a valid image. Choose a JPEG, PNG or WebP photograph.") from error

    if len(result) > MAX_PROFILE_PHOTO_BYTES:
        raise ValueError("The processed photograph is too large. Choose a smaller image.")
    return result


def upload_private_profile_photo(student_id, image_bytes):
    """Upload a processed student image to a private Vercel Blob store."""
    try:
        from vercel.blob import AsyncBlobClient

        async def upload():
            async with AsyncBlobClient() as client:
                return await asyncio.wait_for(
                    client.put(
                        f"student-profiles/{int(student_id)}/{secrets.token_hex(16)}.jpg",
                        image_bytes,
                        access="private",
                        content_type="image/jpeg",
                        add_random_suffix=True,
                        cache_control_max_age=60,
                    ),
                    timeout=8,
                )

        uploaded = asyncio.run(upload())
        pathname = getattr(uploaded, "pathname", None) or getattr(getattr(uploaded, "blob", None), "pathname", None)
        if not pathname:
            raise PhotoStorageError("The image service did not return a storage path.")
        return pathname
    except PhotoStorageError:
        raise
    except Exception as error:
        raise PhotoStorageError("The profile photograph could not be stored securely.") from error


def read_private_profile_photo(pathname):
    if not pathname or not str(pathname).startswith("student-profiles/"):
        raise PhotoStorageError("The requested profile photograph is unavailable.")
    try:
        from vercel.blob import AsyncBlobClient

        async def retrieve():
            async with AsyncBlobClient() as client:
                result = await asyncio.wait_for(client.get(str(pathname), access="private"), timeout=8)
                if result is None or getattr(result, "status_code", 0) != 200 or result.stream is None:
                    return None

                async def collect():
                    return b"".join([chunk async for chunk in result.stream])

                return await asyncio.wait_for(collect(), timeout=8)

        return asyncio.run(retrieve())
    except Exception as error:
        raise PhotoStorageError("The profile photograph could not be retrieved securely.") from error


def delete_private_profile_photo(pathname):
    if not pathname or not str(pathname).startswith("student-profiles/"):
        return
    try:
        from vercel.blob import AsyncBlobClient

        async def remove():
            async with AsyncBlobClient() as client:
                await asyncio.wait_for(client.delete([str(pathname)]), timeout=5)

        asyncio.run(remove())
    except Exception:
        # A failed cleanup leaves an orphaned private blob, not an exposed file.
        return
