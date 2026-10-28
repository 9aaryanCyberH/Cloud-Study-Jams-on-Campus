"""CloudPort confirmation emailer.

Pub/Sub-triggered Cloud Function (2nd gen, Python). Runs when the registration
function publishes an event and sends a confirmation email through SendGrid.

The SendGrid API key is read from Secret Manager at runtime; it is never in
code, environment files or git. If the secret has no version yet, the function
logs a warning and skips the email, so the registration pipeline still works.
"""
import base64
import html
import json
import os
import sys
import urllib.error
import urllib.request

try:
    import functions_framework
except ImportError:
    class _MockFF:
        @staticmethod
        def cloud_event(fn):
            return fn
    functions_framework = _MockFF()

try:
    from google.cloud import secretmanager
except ImportError:
    class _MockSecretManager:
        class SecretManagerServiceClient:
            pass
    secretmanager = _MockSecretManager()

PROJECT_ID = os.environ.get("PROJECT_ID", "")
SECRET_NAME = os.environ.get("SENDGRID_SECRET", "cloudport-sendgrid-api-key")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "")
FROM_NAME = os.environ.get("FROM_NAME", "GDG on Campus BPPIMT")

_secrets = secretmanager.SecretManagerServiceClient()
_UNSET = object()
_cached_key = _UNSET  # None means "looked up, not available"


def log(severity, message, **fields):
    print(json.dumps({"severity": severity, "message": message, **fields}), file=sys.stdout, flush=True)


def _get_api_key():
    global _cached_key
    if _cached_key is not _UNSET:
        return _cached_key
    try:
        name = f"projects/{PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest"
        _cached_key = _secrets.access_secret_version(request={"name": name}).payload.data.decode("utf-8").strip() or None
    except Exception as exc:  # noqa: BLE001
        log("WARNING", "SendGrid key not available in Secret Manager; skipping email", error=str(exc))
        _cached_key = None
    return _cached_key


@functions_framework.cloud_event
def send_confirmation(cloud_event):
    message = (cloud_event.data or {}).get("message") or {}
    raw = message.get("data")
    if not raw:
        log("WARNING", "Event had no message data; ignoring")
        return

    try:
        reg = json.loads(base64.b64decode(raw).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        log("WARNING", "Event payload was not valid JSON; ignoring")
        return
    if not reg.get("email"):
        return

    api_key = _get_api_key()
    if not api_key or not FROM_EMAIL:
        log("INFO", "Email not configured (missing key or FROM_EMAIL). Registration stored, email skipped.", id=reg.get("id"))
        return

    name = html.escape(str(reg.get("name") or "there"))
    interest = html.escape(str(reg.get("interest") or "cloud"))
    body = {
        "personalizations": [{"to": [{"email": reg["email"]}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": "You're registered for the GDG Cloud Workshop",
        "content": [{
            "type": "text/html",
            "value": (
                f"<p>Hi {name},</p>"
                "<p>Thanks for registering for the GDG on Campus BPPIMT Cloud Workshop. "
                f"We saw you are interested in <b>{interest}</b>, so you are in for a good session.</p>"
                "<p>We will share the venue and schedule soon.</p>"
                "<p>- GDG on Campus BPPIMT</p>"
            ),
        }],
    }
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"SendGrid responded with HTTP {exc.code}") from exc

    log("INFO", "Confirmation email sent", id=reg.get("id"))
