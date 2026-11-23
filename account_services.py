"""Account-claim, email-delivery and private profile-photo services."""
import asyncio
import hashlib
import html
import hmac
import json
import logging
import inspect
from importlib.metadata import PackageNotFoundError, version
import os
import re
import secrets
import urllib.error
import urllib.request
from urllib.parse import unquote, urlsplit
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

    def __init__(self, message, reason="storage_unavailable"):
        super().__init__(message)
        self.reason = reason


def _blob_token():
    token = (os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip()
    if not token:
        raise PhotoStorageError("Private photo storage is unavailable.", "missing_blob_token")
    return token


def _blob_error(operation, error):
    # No provider error message, URL, path, token or image data in logs.
    error_type = type(error).__name__
    if isinstance(error, TimeoutError):
        reason = "blob_timeout"
    elif isinstance(error, (ImportError, AttributeError, TypeError)):
        reason = "blob_sdk_incompatible"
    elif "Access" in error_type or "Forbidden" in error_type or "Unauthorized" in error_type:
        reason = "blob_access_denied"
    elif "NotFound" in error_type or "Suspended" in error_type:
        reason = "blob_store_unavailable"
    else:
        reason = "blob_provider_error"
    try:
        sdk_version = version("vercel")
    except PackageNotFoundError:
        sdk_version = "not-installed"
    logging.getLogger(__name__).warning(
        "Photo storage operation=%s reason=%s exception=%s sdk_version=%s",
        operation, reason, error_type, sdk_version,
    )
    return PhotoStorageError("Private photo storage is temporarily unavailable.", reason)


async def _close_blob_client(client):
    # The SDK examples use direct method calls, not a context manager.
    close = getattr(client, "aclose", None) or getattr(client, "close", None)
    if callable(close):
        try:
            result = close()
            if inspect.isawaitable(result):
                await asyncio.wait_for(result, timeout=2)
        except Exception:
            logging.getLogger(__name__).warning("Photo storage client cleanup failed")



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


def _nylas_email_config():
    """Return validated Nylas Transactional Send settings or raise safely."""
    api_key = (os.environ.get("NYLAS_API_KEY") or "").strip()
    domain = (os.environ.get("NYLAS_DOMAIN") or "").strip().lower().rstrip(".")
    sender_email = (os.environ.get("NYLAS_FROM_EMAIL") or "").strip()
    sender_name = (os.environ.get("NYLAS_FROM_NAME") or "StudentVerifi").strip() or "StudentVerifi"
    api_base_url = (
        os.environ.get("NYLAS_API_BASE_URL")
        or os.environ.get("NYLAS_API_URI")
        or "https://api.us.nylas.com"
    ).strip().rstrip("/")
    reply_to = (os.environ.get("NYLAS_REPLY_TO") or "").strip()

    if not api_key or not domain or not sender_email:
        raise EmailDeliveryError("Nylas transactional email is not configured.")

    domain_pattern = r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}"
    if not re.fullmatch(domain_pattern, domain):
        raise EmailDeliveryError("Nylas sending-domain configuration is invalid.")

    email_pattern = r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$"
    if not re.fullmatch(email_pattern, sender_email):
        raise EmailDeliveryError("Nylas sender-email configuration is invalid.")
    sender_domain = sender_email.rsplit("@", 1)[1].lower()
    if sender_domain != domain:
        raise EmailDeliveryError("The Nylas sender address must use the verified sending domain.")
    if reply_to and not re.fullmatch(email_pattern, reply_to):
        raise EmailDeliveryError("Nylas reply-to configuration is invalid.")

    try:
        parsed = urlsplit(api_base_url)
        parsed_port = parsed.port
    except ValueError as error:
        raise EmailDeliveryError("Nylas API region configuration is invalid.") from error
    allowed_hosts = {"api.us.nylas.com", "api.eu.nylas.com"}
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username
        or parsed.password
        or parsed_port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise EmailDeliveryError("Nylas API region configuration is invalid.")

    return {
        "api_key": api_key,
        "domain": domain,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "api_base_url": api_base_url,
        "reply_to": reply_to,
    }


def email_delivery_is_configured():
    """Return whether all required Nylas Transactional Send settings are valid."""
    try:
        _nylas_email_config()
        return True
    except EmailDeliveryError:
        return False


def send_transactional_email(to_address, subject, html_body, idempotency_key=None):
    """Send an HTML transactional email through Nylas Transactional Send."""
    config = _nylas_email_config()
    recipient = str(to_address or "").strip()
    if not re.fullmatch(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$", recipient):
        raise EmailDeliveryError("The transactional email recipient is invalid.")

    payload = {
        "to": [{"email": recipient}],
        "from": {
            "name": config["sender_name"],
            "email": config["sender_email"],
        },
        "subject": str(subject),
        "body": str(html_body),
        "is_plaintext": False,
    }
    if config["reply_to"]:
        payload["reply_to"] = [{"email": config["reply_to"]}]

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = str(idempotency_key)[:256]

    request = urllib.request.Request(
        f"{config['api_base_url']}/v3/domains/{config['domain']}/messages/send",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status < 200 or response.status >= 300:
                raise EmailDeliveryError("Nylas rejected the transactional email.")
            raw_response = response.read(8192)
            if not raw_response:
                return {}
            try:
                return json.loads(raw_response.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {}
    except urllib.error.HTTPError as error:
        # Never expose provider response bodies, recipient addresses or API secrets.
        raise EmailDeliveryError(f"Nylas returned HTTP {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise EmailDeliveryError("Nylas could not be reached to deliver the email.") from error


def _email_brand_origin():
    base = (os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
    try:
        parsed = urlsplit(base)
        if (parsed.scheme == "https" and parsed.hostname and not parsed.username and
                not parsed.password and parsed.path in ("", "/") and not parsed.query and
                not parsed.fragment and parsed.port in (None, 443)):
            return base
    except ValueError:
        pass
    return ""


def render_branded_email(title, introduction, content, security_note, preheader):
    """Shared email presentation; content is constructed by trusted templates."""
    origin = _email_brand_origin()
    home = html.escape(origin, quote=True)
    logo = (f'<img src="{home}/email-logo.png" width="260" height="60" alt="StudentVerifi" '
            'style="display:block;width:260px;max-width:100%;height:auto;border:0;margin:0 auto;">'
            if origin else '<strong style="font-size:24px;color:#17243a">StudentVerifi</strong>')
    institution = html.escape(os.environ.get("INSTITUTION_NAME") or "Ebonyi State University")
    footer_link = (f'<a href="{home}" style="color:#155b87;text-decoration:underline">Visit StudentVerifi</a>'
                   if origin else 'StudentVerifi')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#eef3f8;color:#17243a;font-family:Arial,Helvetica,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef3f8;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #dce5ef;border-radius:16px;overflow:hidden;">
<tr><td style="background:#155b87;height:6px;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td align="center" style="padding:28px 24px 22px;border-bottom:1px solid #e6edf4;">{logo}<p style="margin:10px 0 0;color:#52627a;font-size:12px;">{institution} &middot; Academic prototype</p></td></tr>
<tr><td style="padding:30px 28px;">
<p style="margin:0 0 9px;color:#0f766e;font-size:11px;letter-spacing:1.8px;font-weight:bold;">STUDENTVERIFI &nbsp; / &nbsp; ACCOUNT SECURITY</p>
<h1 style="margin:0 0 16px;font-size:25px;line-height:1.3;color:#17243a;">{html.escape(title)}</h1>
<p style="margin:0 0 20px;font-size:15px;line-height:1.65;color:#45556b;">{html.escape(introduction)}</p>
{content}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;background:#f4f8fb;border-radius:8px;border:1px solid #e1e9f0;"><tr><td style="padding:15px;font-size:13px;line-height:1.6;color:#45556b;"><strong style="color:#17243a;">Keep your account secure</strong><br>{html.escape(security_note)}</td></tr></table>
</td></tr><tr><td align="center" style="padding:20px 24px;background:#f6f8fb;border-top:1px solid #e6edf4;color:#52627a;font-size:12px;line-height:1.7;">{footer_link}<br>This is an automated account email. Never share your verification code or invitation link.</td></tr>
</table></td></tr></table></body></html>"""


def send_claim_otp(to_address, otp, challenge_id, institution_name="StudentVerifi"):
    code = html.escape(str(otp))
    content = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#edf5fc;border:1px solid #d6e6f5;border-radius:10px;"><tr><td align="center" style="padding:20px 8px;">'
        '<p style="margin:0 0 7px;color:#52627a;font-size:12px;font-weight:bold;letter-spacing:1px;">YOUR VERIFICATION CODE</p>'
        f'<p style="margin:0;color:#1d4ed8;font-family:Arial,sans-serif;font-size:34px;font-weight:bold;letter-spacing:6px;">{code}</p>'
        f'<p style="margin:11px 0 0;color:#45556b;font-size:13px;">Expires in {OTP_TTL_MINUTES} minutes &middot; Single use</p></td></tr></table>'
    )
    body = render_branded_email("Verify your email", "Enter the code below in StudentVerifi to confirm your email address.", content,
        "Do not share this code with anyone. If you did not request it, simply ignore this email.",
        "Your StudentVerifi verification code is ready.")
    send_transactional_email(to_address, "StudentVerifi | Your verification code", body,
                             idempotency_key=f"student-claim-otp/{challenge_id}")


def send_verifier_invitation(to_address, display_name, invitation_url, invitation_id):
    safe_url = html.escape(invitation_url, quote=True)
    content = (
        '<table role="presentation" cellspacing="0" cellpadding="0" style="margin:22px auto;"><tr><td align="center" bgcolor="#155b87" style="border-radius:8px;">'
        f'<a href="{safe_url}" style="display:inline-block;color:#ffffff;font-size:15px;font-weight:bold;padding:14px 24px;text-decoration:none;">Accept invitation</a></td></tr></table>'
        '<p style="color:#45556b;font-size:13px;line-height:1.6;">This invitation expires in 48 hours. If the button does not work, copy this address into your browser:</p>'
        f'<p style="font-size:12px;word-break:break-all;overflow-wrap:anywhere;"><a href="{safe_url}" style="color:#155b87;">{safe_url}</a></p>'
    )
    body = render_branded_email("You are invited", f"Hello {display_name or 'colleague'}, you have been invited to join StudentVerifi as an authorised verifier.", content,
        "Only accept an invitation you were expecting. This link is personal and must not be forwarded.",
        "Your invitation to join StudentVerifi.")
    send_transactional_email(to_address, "StudentVerifi | Verifier invitation", body,
                             idempotency_key=f"verifier-invitation/{invitation_id}")


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
        token = _blob_token()
        from vercel.blob import AsyncBlobClient

        async def upload():
            client = AsyncBlobClient(token=token)
            try:
                return await asyncio.wait_for(client.put(
                    f"student-profiles/{int(student_id)}/{secrets.token_hex(16)}.jpg",
                    image_bytes, access="private", content_type="image/jpeg",
                    add_random_suffix=True,
                ), timeout=20)
            finally:
                await _close_blob_client(client)

        uploaded = asyncio.run(upload())
        pathname = getattr(uploaded, "pathname", None)
        if not pathname or not pathname.startswith(f"student-profiles/{int(student_id)}/"):
            raise PhotoStorageError("The image service did not return a storage path.", "blob_invalid_response")
        return pathname
    except PhotoStorageError:
        raise
    except Exception as error:
        raise _blob_error("upload", error) from None


def _validate_private_blob_url(blob_url, pathname):
    """Accept only the exact private Vercel Blob URL returned by SDK metadata."""
    try:
        parsed = urlsplit(str(blob_url or ""))
        port = parsed.port
    except ValueError as error:
        raise PhotoStorageError("The stored photograph address is invalid.", "blob_metadata_invalid") from error

    hostname = (parsed.hostname or "").lower()
    expected_path = str(pathname or "")
    actual_path = unquote(parsed.path.lstrip("/"))
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".private.blob.vercel-storage.com")
        or hostname == ".private.blob.vercel-storage.com"
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or actual_path != expected_path
    ):
        raise PhotoStorageError("The stored photograph address is invalid.", "blob_metadata_invalid")
    return str(blob_url)


def _private_blob_download_url(pathname, token):
    """Resolve a private Blob URL through the official SDK metadata operation.

    Do not infer the store ID from the token: Vercel may change credential
    formats and the SDK already knows how to authenticate metadata requests.
    """
    path = str(pathname or "")
    segments = path.split("/")
    if (
        len(segments) != 3
        or segments[0] != "student-profiles"
        or not segments[1].isdigit()
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", segments[2])
        or segments[2] in {".", ".."}
    ):
        raise PhotoStorageError("The requested profile photograph is unavailable.", "blob_path_invalid")

    from vercel.blob import AsyncBlobClient

    async def resolve():
        client = AsyncBlobClient(token=token)
        try:
            metadata = await asyncio.wait_for(client.head(path), timeout=12)
            if metadata is None:
                return None
            blob_url = getattr(metadata, "url", None)
            if not blob_url:
                raise PhotoStorageError(
                    "The storage service did not return photograph metadata.",
                    "blob_metadata_invalid",
                )
            return _validate_private_blob_url(blob_url, path)
        finally:
            await _close_blob_client(client)

    try:
        return asyncio.run(resolve())
    except PhotoStorageError:
        raise
    except Exception as error:
        raise _blob_error("metadata", error) from None


def read_private_profile_photo(pathname):
    """Read a private photograph using Vercel's documented Bearer-token HTTP access."""
    token = _blob_token()
    url = _private_blob_download_url(pathname, token)
    if not url:
        logging.getLogger(__name__).warning(
            "Photo storage operation=read reason=blob_not_found"
        )
        return None
    blob_request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "image/jpeg",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(blob_request, timeout=15) as response:
            status = getattr(response, "status", None) or response.getcode()
            if status != 200:
                logging.getLogger(__name__).warning(
                    "Photo storage operation=read reason=blob_http_status status=%s", status
                )
                return None

            content_type = (response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower())
            if content_type not in {"image/jpeg", "image/jpg"}:
                logging.getLogger(__name__).warning(
                    "Photo storage operation=read reason=blob_content_type_invalid content_type=%s",
                    content_type or "missing",
                )
                raise PhotoStorageError(
                    "The stored profile photograph has an invalid content type.",
                    "blob_content_type_invalid",
                )

            image_bytes = response.read(MAX_PROFILE_PHOTO_BYTES + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            logging.getLogger(__name__).warning(
                "Photo storage operation=read reason=blob_not_found status=404"
            )
            return None
        if error.code in {401, 403}:
            reason = "blob_access_denied"
        else:
            reason = "blob_http_error"
        logging.getLogger(__name__).warning(
            "Photo storage operation=read reason=%s status=%s", reason, error.code
        )
        raise PhotoStorageError(
            "Private photo storage is temporarily unavailable.", reason
        ) from None
    except (TimeoutError, urllib.error.URLError, OSError) as error:
        reason = "blob_timeout" if isinstance(error, TimeoutError) else "blob_network_error"
        logging.getLogger(__name__).warning(
            "Photo storage operation=read reason=%s exception=%s", reason, type(error).__name__
        )
        raise PhotoStorageError(
            "Private photo storage is temporarily unavailable.", reason
        ) from None

    if len(image_bytes) > MAX_PROFILE_PHOTO_BYTES:
        raise PhotoStorageError("The stored photograph is too large.", "blob_invalid_response")
    if not image_bytes or not image_bytes.startswith(b"\xff\xd8\xff"):
        raise PhotoStorageError("The stored profile photograph is not a valid JPEG.", "blob_invalid_response")
    return image_bytes


def delete_private_profile_photo(pathname):
    if not pathname or not str(pathname).startswith("student-profiles/"):
        return
    try:
        token = _blob_token()
        from vercel.blob import AsyncBlobClient

        async def remove():
            client = AsyncBlobClient(token=token)
            try:
                await asyncio.wait_for(client.delete([str(pathname)]), timeout=8)
            finally:
                await _close_blob_client(client)

        asyncio.run(remove())
    except Exception as error:
        # A failed cleanup leaves an orphaned private blob, not an exposed file.
        logging.getLogger(__name__).warning("Photo cleanup failed: %s", type(error).__name__)
