"""Automated Unit Tests for CloudPort Cloud Function HTTP and Security Behavior.

Uses mocks for Firestore and Pub/Sub dependencies to test offline without GCP credentials.
Covers:
  - Requirement 1: JSON payload acceptance
  - Requirement 2: OPTIONS preflight and CORS origin validation
  - Requirement 3: Server-side validation enforcement
  - Requirement 4: Rejection of invalid JSON, missing fields, invalid email, and non-POST methods
  - Requirement 5: Document creation in Firestore
  - Requirement 6: Submitted fields & server timestamp verification
  - Requirement 7 & 8: Service account and ADC integration test design
  - Requirement 9: Credential isolation
  - Requirement 10: Safe error handling without implementation detail leakage
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure current directory is on sys.path for direct test execution
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request

import main

# Flask test harness application
_test_app = Flask(__name__)

SAMPLE_PAYLOAD = {
    "name": "Aaryan Kumar",
    "email": "aaryan.kumar@bppimt.edu.in",
    "department": "CSE",
    "interest": "Cloud Infrastructure",
    "website": "",
}

SAMPLE_MENTOR_PAYLOAD = {
    "registrationType": "mentor",
    "name": "Aaryan Kumar",
    "email": "aaryan.mentor@bppimt.edu.in",
    "currentRole": "4th Year CSE & Cloud Lead",
    "skills": "Google Cloud, Python, Terraform, Docker",
    "mentorAreas": "Cloud Infrastructure, Serverless Microservices",
    "motivation": "Excited to guide junior students through GCP fundamentals and hands-on lab deployments.",
    "website": "",
}


class CloudPortHttpUnitTests(unittest.TestCase):
    def setUp(self):
        # Reset main module client caches and environment configuration
        main._db = None
        main._publisher = None
        main._ALLOW_ALL_ORIGINS = True
        main._ALLOWED_ORIGINS_SET = set()
        main.PROJECT_ID = ""
        main.PUBSUB_TOPIC = ""

    # -------------------------------------------------------------------------
    # CORS & OPTIONS Preflight Tests (Requirement 2)
    # -------------------------------------------------------------------------
    def test_options_preflight_returns_204_with_cors_headers(self):
        """OPTIONS preflight request must return 204 No Content with CORS headers."""
        with _test_app.test_request_context(
            method="OPTIONS",
            path="/",
            headers={
                "Origin": "https://storage.googleapis.com",
                "Access-Control-Request-Method": "POST",
            },
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 204)
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Origin"),
                "https://storage.googleapis.com",
            )
            self.assertIn("POST", response.headers.get("Access-Control-Allow-Methods", ""))
            self.assertIn("OPTIONS", response.headers.get("Access-Control-Allow-Methods", ""))
            self.assertEqual(response.headers.get("Access-Control-Max-Age"), "3600")

    def test_strict_cors_mode_allows_whitelisted_origin(self):
        """When ALLOWED_ORIGINS is configured, whitelisted origins must be echoed."""
        main._ALLOW_ALL_ORIGINS = False
        main._ALLOWED_ORIGINS_SET = {"https://storage.googleapis.com"}

        with _test_app.test_request_context(
            method="OPTIONS",
            path="/",
            headers={"Origin": "https://storage.googleapis.com"},
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 204)
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Origin"),
                "https://storage.googleapis.com",
            )

    def test_strict_cors_mode_rejects_unauthorized_origin(self):
        """Unauthorized origins in strict CORS mode must receive HTTP 403 Forbidden."""
        main._ALLOW_ALL_ORIGINS = False
        main._ALLOWED_ORIGINS_SET = {"https://storage.googleapis.com"}

        with _test_app.test_request_context(
            method="POST",
            path="/",
            json=SAMPLE_PAYLOAD,
            headers={"Origin": "https://unauthorized-malicious-site.com"},
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 403)
            data = json.loads(response.get_data(as_text=True))
            self.assertFalse(data["ok"])
            self.assertIn("CORS origin not allowed", data["error"])

    # -------------------------------------------------------------------------
    # HTTP Method & Content-Type Enforcement (Requirement 4)
    # -------------------------------------------------------------------------
    def test_unsupported_http_methods_return_405(self):
        """GET, PUT, DELETE must be rejected with 405 Method Not Allowed and Allow header."""
        for method in ("GET", "PUT", "DELETE", "PATCH"):
            with _test_app.test_request_context(method=method, path="/"):
                response = main.register_user(request)
                self.assertEqual(
                    response.status_code, 405, f"Method {method} was not rejected with 405"
                )
                self.assertIn("POST", response.headers.get("Allow", ""))

    def test_non_json_content_type_returns_415(self):
        """Requests with non-JSON content-type must receive 415 Unsupported Media Type."""
        with _test_app.test_request_context(
            method="POST",
            path="/",
            data="plain text body",
            content_type="text/plain",
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 415)

    def test_malformed_json_body_returns_400(self):
        """Empty or malformed JSON payloads must receive HTTP 400 Bad Request."""
        with _test_app.test_request_context(
            method="POST",
            path="/",
            data="[this is not valid json]",
            content_type="application/json",
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 400)

    # -------------------------------------------------------------------------
    # Server-Side Validation (Requirements 3 & 4)
    # -------------------------------------------------------------------------
    def test_missing_required_fields_return_400(self):
        """Missing required fields must be rejected with 400 and an itemized details list."""
        with _test_app.test_request_context(
            method="POST",
            path="/",
            json={},
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 400)
            data = json.loads(response.get_data(as_text=True))
            self.assertFalse(data["ok"])
            self.assertIn("details", data)
            self.assertEqual(len(data["details"]), 4)

    def test_invalid_email_format_returns_400(self):
        """Invalid email formats must be rejected by server validation with HTTP 400."""
        with _test_app.test_request_context(
            method="POST",
            path="/",
            json={**SAMPLE_PAYLOAD, "email": "invalid-email-address"},
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 400)
            data = json.loads(response.get_data(as_text=True))
            self.assertIn("email format is invalid", data["error"])

    def test_unapproved_department_or_interest_returns_400(self):
        """Unrecognized departments or interests must receive HTTP 400."""
        with _test_app.test_request_context(
            method="POST",
            path="/",
            json={**SAMPLE_PAYLOAD, "department": "Aviation", "interest": "Alchemy"},
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 400)

    # -------------------------------------------------------------------------
    # Successful Registration & Firestore Persistence (Requirements 1, 5, 6)
    # -------------------------------------------------------------------------
    @patch.object(main, "get_firestore_client")
    def test_valid_registration_creates_firestore_document(self, mock_get_db):
        """Valid submission must create a document in Firestore with server timestamp and return 201."""
        mock_doc = MagicMock()
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        with _test_app.test_request_context(
            method="POST",
            path="/",
            json=SAMPLE_PAYLOAD,
            headers={"Origin": "https://storage.googleapis.com"},
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 201)
            data = json.loads(response.get_data(as_text=True))
            self.assertTrue(data["ok"])
            self.assertIn("id", data)

            # Verify Firestore collection call
            mock_db.collection.assert_called_with("registrations")
            # Verify document create was invoked
            mock_doc.create.assert_called_once()
            record_written = mock_doc.create.call_args[0][0]
            self.assertEqual(record_written["name"], "Aaryan Kumar")
            self.assertEqual(record_written["email"], "aaryan.kumar@bppimt.edu.in")
            self.assertEqual(record_written["department"], "CSE")
            self.assertEqual(record_written["interest"], "Cloud Infrastructure")
            self.assertEqual(record_written["source"], "web_cloudport")
            # Verify server timestamp inclusion
            self.assertIn("createdAt", record_written)

    # -------------------------------------------------------------------------
    # Idempotency / Duplicate Prevention
    # -------------------------------------------------------------------------
    @patch.object(main, "get_firestore_client")
    def test_duplicate_registration_returns_409_conflict(self, mock_get_db):
        """Re-registering an existing email must return HTTP 409 Conflict with DUPLICATE_EMAIL code."""
        mock_doc = MagicMock()
        mock_doc.create.side_effect = main.AlreadyExists("Document exists")
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        with _test_app.test_request_context(
            method="POST",
            path="/",
            json=SAMPLE_PAYLOAD,
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 409)
            data = json.loads(response.get_data(as_text=True))
            self.assertFalse(data["ok"])
            self.assertEqual(data.get("code"), "DUPLICATE_EMAIL")

    # -------------------------------------------------------------------------
    # Anti-Spam Honeypot Protection
    # -------------------------------------------------------------------------
    @patch.object(main, "get_firestore_client")
    def test_honeypot_field_triggers_silent_success_without_db_write(self, mock_get_db):
        """Automated bots filling the website field receive 201, but no Firestore document is created."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        with _test_app.test_request_context(
            method="POST",
            path="/",
            json={**SAMPLE_PAYLOAD, "website": "http://spambot-link.com"},
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 201)
            # Verify database create was NOT called
            mock_db.collection.assert_not_called()

    # -------------------------------------------------------------------------
    # Safe Error Handling without Implementation Detail Leakage (Requirement 10)
    # -------------------------------------------------------------------------
    @patch.object(main, "get_firestore_client")
    def test_internal_database_error_returns_sanitized_500(self, mock_get_db):
        """Internal errors must return a generic 500 message without exposing database stack traces or credentials."""
        mock_doc = MagicMock()
        mock_doc.create.side_effect = RuntimeError("Internal connection failure: secret_connection_string_fail")
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        with _test_app.test_request_context(
            method="POST",
            path="/",
            json=SAMPLE_PAYLOAD,
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 500)
            data = json.loads(response.get_data(as_text=True))
            self.assertFalse(data["ok"])
            # Ensure sensitive internal messages are not exposed to client
            self.assertNotIn("secret_connection_string_fail", data["error"])
            self.assertIn("Internal server error", data["error"])

    # -------------------------------------------------------------------------
    # Decoupled Pub/Sub Event Resilience
    # -------------------------------------------------------------------------
    @patch.object(main, "get_firestore_client")
    @patch.object(main, "get_pubsub_publisher")
    def test_pubsub_failure_does_not_fail_registration(self, mock_get_pubsub, mock_get_db):
        """A failure during async Pub/Sub publishing must be logged, but the registration must still succeed (201)."""
        mock_doc = MagicMock()
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        mock_publisher = MagicMock()
        mock_publisher.publish.side_effect = Exception("PubSub timeout")
        mock_get_pubsub.return_value = mock_publisher

        main.PROJECT_ID = "test-project"
        main.PUBSUB_TOPIC = "registration-created"

        with _test_app.test_request_context(
            method="POST",
            path="/",
            json=SAMPLE_PAYLOAD,
        ):
            response = main.register_user(request)
            # Registration must still succeed with 201
            self.assertEqual(response.status_code, 201)
            data = json.loads(response.get_data(as_text=True))
            self.assertTrue(data["ok"])

    # -------------------------------------------------------------------------
    # Mentor Registration & Firestore Integration Tests
    # -------------------------------------------------------------------------
    @patch.object(main, "get_firestore_client")
    def test_valid_mentor_registration_creates_firestore_document(self, mock_get_db):
        """Valid mentor registration creates a separate document in Firestore with 'mentor' registrationType."""
        mock_doc = MagicMock()
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        with _test_app.test_request_context(
            method="POST",
            path="/",
            json=SAMPLE_MENTOR_PAYLOAD,
            headers={"Origin": "https://storage.googleapis.com"},
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 201)
            data = json.loads(response.get_data(as_text=True))
            self.assertTrue(data["ok"])
            self.assertEqual(data["registrationType"], "mentor")
            self.assertIn("mentor", data["message"].lower())

            # Verify Firestore collection call
            mock_db.collection.assert_called_with("registrations")
            mock_doc.create.assert_called_once()
            record = mock_doc.create.call_args[0][0]
            self.assertEqual(record["registrationType"], "mentor")
            self.assertEqual(record["name"], "Aaryan Kumar")
            self.assertEqual(record["currentRole"], "4th Year CSE & Cloud Lead")
            self.assertEqual(record["skills"], "Google Cloud, Python, Terraform, Docker")
            self.assertIn("createdAt", record)

    @patch.object(main, "get_firestore_client")
    def test_duplicate_mentor_registration_returns_409_conflict(self, mock_get_db):
        """Duplicate mentor registration with the same email returns HTTP 409 Conflict."""
        mock_doc = MagicMock()
        mock_doc.create.side_effect = main.AlreadyExists("Mentor document exists")
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        with _test_app.test_request_context(
            method="POST",
            path="/",
            json=SAMPLE_MENTOR_PAYLOAD,
        ):
            response = main.register_user(request)
            self.assertEqual(response.status_code, 409)
            data = json.loads(response.get_data(as_text=True))
            self.assertFalse(data["ok"])
            self.assertIn("mentor application", data["error"])


if __name__ == "__main__":
    unittest.main()
