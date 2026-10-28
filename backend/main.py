"""CloudPort registration endpoint.

HTTP-triggered Google Cloud Function (2nd Gen, Python runtime).
Features:
  1. Handles CORS preflight (OPTIONS) and origin validation.
  2. Validates JSON payload schema and sanitizes input.
  3. Rejects invalid email formats, missing fields, or empty values.
  4. Honeypot check for bot detection.
  5. Idempotent storage in Firestore collection `registrations` with server timestamp.
  6. Returns structured JSON with proper HTTP status codes.
  7. Pub/Sub event publishing for decoupled async processing (e.g., confirmation email).
  8. Zero hardcoded secrets: relies solely on GCP Runtime Service Account and ADC.
"""
import hashlib
import json
import os
import sys

try:
    import functions_framework
except ImportError:
    class _MockFunctionsFramework:
        @staticmethod
        def http(fn):
            return fn
        @staticmethod
        def cloud_event(fn):
            return fn
    functions_framework = _MockFunctionsFramework()

from flask import jsonify

try:
    from google.cloud import firestore, pubsub_v1
    from google.api_core.exceptions import AlreadyExists
    GCP_LIBS_AVAILABLE = True
except ImportError:
    GCP_LIBS_AVAILABLE = False
    class _FirestoreStub:
        SERVER_TIMESTAMP = "MOCK_SERVER_TIMESTAMP"
        class Client:
            pass
    firestore = _FirestoreStub()
    pubsub_v1 = None
    class AlreadyExists(Exception):
        pass

from validate import validate_registration

# Configuration from Environment Variables
COLLECTION = os.environ.get("COLLECTION", "registrations")
PROJECT_ID = os.environ.get("PROJECT_ID", "")
PUBSUB_TOPIC = os.environ.get("PUBSUB_TOPIC", "")
RAW_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")

# Parse allowed origins list
_ALLOWED_ORIGINS_SET = {o.strip() for o in RAW_ORIGINS.split(",") if o.strip()}
_ALLOW_ALL_ORIGINS = "*" in _ALLOWED_ORIGINS_SET or not _ALLOWED_ORIGINS_SET

# Lazy-loaded GCP client singletons
_db = None
_publisher = None


# Local in-memory store for offline development when GCP libraries are absent
class _LocalDevDocument:
    def __init__(self, col, doc_id):
        self.col = col
        self.doc_id = doc_id

    def create(self, data):
        if self.doc_id in self.col._docs:
            raise AlreadyExists(f"Document {self.doc_id} already exists")
        from datetime import datetime, timezone
        stored = dict(data)
        stored["createdAt"] = datetime.now(timezone.utc).isoformat()
        self.col._docs[self.doc_id] = stored
        return True

class _LocalDevCollection:
    def __init__(self, name):
        self.name = name
        self._docs = {}

    def document(self, doc_id):
        return _LocalDevDocument(self, doc_id)

class _LocalDevDatabase:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = _LocalDevCollection(name)
        return self._collections[name]

_local_dev_db_instance = _LocalDevDatabase()

def get_firestore_client():
    """Lazily initialize Firestore client to allow testing, emulator, and local dev."""
    global _db
    if _db is None:
        if not GCP_LIBS_AVAILABLE or os.environ.get("LOCAL_DEV", "").lower() in ("true", "1", "yes"):
            if not GCP_LIBS_AVAILABLE or os.environ.get("LOCAL_DEV", "").lower() in ("true", "1", "yes"):
                log("INFO", "Running with Local Dev database storage")
                _db = _local_dev_db_instance
                return _db
            raise RuntimeError("google-cloud-firestore is not installed")
        # Automatically detects Application Default Credentials or FIRESTORE_EMULATOR_HOST
        project = PROJECT_ID or os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or None
        _db = firestore.Client(project=project)
    return _db


def get_pubsub_publisher():
    """Lazily initialize Pub/Sub client."""
    global _publisher
    if _publisher is None and GCP_LIBS_AVAILABLE:
        try:
            _publisher = pubsub_v1.PublisherClient()
        except Exception as exc:
            log("WARNING", "Pub/Sub client initialization skipped", error=str(exc))
            _publisher = None
    return _publisher


def log(severity, message, **fields):
    """Structured JSON logging formatted for Cloud Logging integration."""
    payload = {"severity": severity, "message": message, **fields}
    print(json.dumps(payload), file=sys.stdout, flush=True)


def _build_response(body, status_code, origin=None, extra_headers=None):
    """Build a JSON response with appropriate CORS headers."""
    response = jsonify(body)
    response.status_code = status_code

    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"

    if extra_headers:
        for header, value in extra_headers.items():
            response.headers[header] = value

    return response


def _get_doc_id(email):
    """Generate a deterministic 32-character SHA-256 hash document ID.

    Ensures idempotency: one registration per unique email, avoiding accidental duplicate submissions.
    """
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]


def _resolve_allowed_origin(request_origin):
    """Determine the Access-Control-Allow-Origin header value."""
    if _ALLOW_ALL_ORIGINS:
        return request_origin or "*"
    if request_origin and request_origin in _ALLOWED_ORIGINS_SET:
        return request_origin
    return None


@functions_framework.http
def register_user(request):
    """HTTP Cloud Function entry point for event registration."""
    request_origin = request.headers.get("Origin")
    effective_origin = _resolve_allowed_origin(request_origin)

    # If Origin is present but not authorized in strict mode, reject
    if request_origin and not _ALLOW_ALL_ORIGINS and request_origin not in _ALLOWED_ORIGINS_SET:
        log("WARNING", "CORS origin rejected", origin=request_origin)
        return _build_response({"ok": False, "error": "CORS origin not allowed"}, 403)

    # 1. Handle CORS Preflight (OPTIONS)
    if request.method == "OPTIONS":
        cors_headers = {
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Max-Age": "3600",
        }
        res = _build_response({}, 204, effective_origin, cors_headers)
        res.set_data(b"")
        return res

    # 2. Enforce HTTP POST
    if request.method != "POST":
        return _build_response(
            {"ok": False, "error": "Method not allowed. Use POST."},
            405,
            effective_origin,
            {"Allow": "POST, OPTIONS"},
        )

    # 3. Enforce Content-Type application/json
    if not request.is_json:
        return _build_response(
            {"ok": False, "error": "Content-Type must be application/json"},
            415,
            effective_origin,
        )

    # 4. Parse JSON body
    body = request.get_json(silent=True)
    if body is None:
        return _build_response(
            {"ok": False, "error": "Malformed or empty JSON payload"},
            400,
            effective_origin,
        )

    # 5. Anti-spam Honeypot check
    # Hidden form field `website` is untouched by humans. Bots autofill it.
    if isinstance(body, dict) and str(body.get("website", "")).strip():
        log("INFO", "Honeypot triggered, pretending success")
        return _build_response({"ok": True, "message": "Registration received"}, 201, effective_origin)

    # 6. Validate input fields
    errors, sanitized_data = validate_registration(body)
    if errors:
        return _build_response(
            {
                "ok": False,
                "error": "; ".join(errors),
                "details": errors,
            },
            400,
            effective_origin,
        )

    # 7. Generate deterministic document ID based on registration type and email
    reg_type = sanitized_data.get("registrationType", "student")
    if reg_type == "mentor":
        doc_id = _get_doc_id(f"mentor:{sanitized_data['email']}")
    else:
        doc_id = _get_doc_id(sanitized_data["email"])

    # 8. Persist to Firestore Native collection
    try:
        db = get_firestore_client()
        registration_record = {
            **sanitized_data,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "source": "web_cloudport",
        }

        # create() enforces that the document does NOT already exist
        db.collection(COLLECTION).document(doc_id).create(registration_record)
        log("INFO", "Registration successfully saved", id=doc_id, email=sanitized_data["email"], type=reg_type)

    except AlreadyExists:
        log("INFO", "Duplicate registration attempt", email=sanitized_data["email"], type=reg_type)
        duplicate_msg = (
            "This email has already submitted a mentor application."
            if reg_type == "mentor"
            else "This email is already registered for the workshop."
        )
        return _build_response(
            {
                "ok": False,
                "error": duplicate_msg,
                "code": "DUPLICATE_EMAIL",
            },
            409,
            effective_origin,
        )
    except Exception as exc:
        # Crucial: Never expose internal database errors or stack traces to clients
        log("ERROR", "Firestore write failed", error=str(exc), id=doc_id)
        return _build_response(
            {
                "ok": False,
                "error": "Internal server error occurred while saving registration. Please try again later.",
            },
            500,
            effective_origin,
        )

    # 9. Asynchronously publish event to Pub/Sub (optional decoupled event)
    if PUBSUB_TOPIC and PROJECT_ID:
        try:
            publisher = get_pubsub_publisher()
            if publisher:
                topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
                event_payload = {
                    "id": doc_id,
                    "registrationType": reg_type,
                    "name": sanitized_data["name"],
                    "email": sanitized_data["email"],
                }
                if reg_type == "student":
                    event_payload["department"] = sanitized_data.get("department", "")
                    event_payload["interest"] = sanitized_data.get("interest", "")
                else:
                    event_payload["currentRole"] = sanitized_data.get("currentRole", "")
                    event_payload["mentorAreas"] = sanitized_data.get("mentorAreas", "")

                publisher.publish(
                    topic_path,
                    json.dumps(event_payload).encode("utf-8"),
                ).result(timeout=5)
                log("INFO", "Pub/Sub event published", id=doc_id, topic=PUBSUB_TOPIC)
        except Exception as exc:
            # Notice: Pub/Sub delivery failure does NOT fail the registration
            log("WARNING", "Pub/Sub publish failed, registration still preserved", error=str(exc), id=doc_id)

    # 10. Success Response
    success_msg = (
        "Mentor application received! Thank you for volunteering with GDG on Campus BPPIMT."
        if reg_type == "mentor"
        else "Registration successful! We look forward to seeing you at the workshop."
    )
    return _build_response(
        {
            "ok": True,
            "message": success_msg,
            "id": doc_id,
            "registrationType": reg_type,
        },
        201,
        effective_origin,
    )
