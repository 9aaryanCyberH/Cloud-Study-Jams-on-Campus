"""Cloud Integration Test Harness for CloudPort.

DISTINCTION:
  - backend/test_main.py: Offline UNIT tests using unittest.mock. Run anytime without GCP.
  - backend/integration_test.py: INTEGRATION tests requiring either:
      a) A live Google Cloud Project with active credentials (gcloud auth application-default login), OR
      b) The Google Cloud Firestore Emulator running locally (gcloud emulators firestore start).

To run against the local emulator:
    export FIRESTORE_EMULATOR_HOST="localhost:8085"
    export PROJECT_ID="local-test-project"
    python backend/integration_test.py
"""
import os
import sys
import unittest

# Check if environment is configured for integration testing
HAS_EMULATOR = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
HAS_GCP_PROJECT = bool(os.environ.get("PROJECT_ID") and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))

if not (HAS_EMULATOR or HAS_GCP_PROJECT):
    print("----------------------------------------------------------------------")
    print("SKIPPED: Live cloud integration tests require either:")
    print("  1. FIRESTORE_EMULATOR_HOST (e.g. localhost:8085), OR")
    print("  2. PROJECT_ID and active Google Cloud credentials.")
    print("To run offline unit tests with mocks, use:")
    print("  python backend/test_main.py")
    print("----------------------------------------------------------------------")
    sys.exit(0)


class CloudPortLiveIntegrationTest(unittest.TestCase):
    def setUp(self):
        import main
        self.main = main

    def test_live_firestore_roundtrip(self):
        """Test actual connection and document write to Firestore."""
        db = self.main.get_firestore_client()
        test_col = os.environ.get("COLLECTION", "registrations_integration_test")
        test_doc_ref = db.collection(test_col).document("integration_test_doc")

        # Write test document
        test_doc_ref.set({
            "name": "Integration Test Runner",
            "email": "test@example.com",
            "department": "CSE",
            "interest": "Cloud Infrastructure",
            "source": "integration_test"
        })

        # Read back document to verify persistence
        snapshot = test_doc_ref.get()
        self.assertTrue(snapshot.exists)
        self.assertEqual(snapshot.get("name"), "Integration Test Runner")

        # Cleanup test document
        test_doc_ref.delete()


if __name__ == "__main__":
    unittest.main()
