import os
import sys
import unittest

# Ensure current directory is on sys.path for direct test execution
sys.path.insert(0, os.path.dirname(__file__))

from validate import (
    validate_registration,
    validate_student_registration,
    validate_mentor_registration,
    DEPARTMENTS,
    INTERESTS,
    YEARS_OF_STUDY,
)

GOOD_PAYLOAD = {
    "name": "Aaryan Kumar",
    "email": "Aaryan.Kumar@example.edu",
    "department": "CSE",
    "interest": "Cloud Infrastructure",
}

GOOD_MENTOR_PAYLOAD = {
    "registrationType": "mentor",
    "name": "Aaryan Kumar",
    "email": "aaryan.mentor@bppimt.edu.in",
    "currentRole": "4th Year CSE & Cloud Lead",
    "skills": "Google Cloud, Python, Terraform, Docker",
    "mentorAreas": "Cloud Infrastructure, Serverless Microservices",
    "motivation": "Excited to guide junior students through GCP fundamentals and hands-on lab deployments.",
}


class ValidateRegistrationTests(unittest.TestCase):
    def test_accepts_valid_payload_and_normalises_email(self):
        errors, value = validate_registration(GOOD_PAYLOAD)
        self.assertEqual(errors, [])
        self.assertIsNotNone(value)
        self.assertEqual(value["email"], "aaryan.kumar@example.edu")
        self.assertEqual(value["name"], "Aaryan Kumar")
        self.assertEqual(value["department"], "CSE")
        self.assertEqual(value["interest"], "Cloud Infrastructure")
        self.assertEqual(value["registrationType"], "student")

    def test_accepts_all_departments_and_interests(self):
        for dept in DEPARTMENTS:
            for interest in INTERESTS:
                payload = {
                    "name": "Student Test",
                    "email": f"test_{dept.lower()}@example.com",
                    "department": dept,
                    "interest": interest,
                }
                errors, value = validate_registration(payload)
                self.assertEqual(errors, [])
                self.assertEqual(value["department"], dept)
                self.assertEqual(value["interest"], interest)

    def test_reports_all_missing_fields_when_empty(self):
        errors, value = validate_registration({})
        self.assertEqual(len(errors), 4)
        self.assertIsNone(value)
        self.assertTrue(any("name" in e for e in errors))
        self.assertTrue(any("email" in e for e in errors))
        self.assertTrue(any("department" in e for e in errors))
        self.assertTrue(any("interest" in e for e in errors))

    def test_rejects_non_dict_bodies(self):
        for invalid_body in (None, [], "string", 12345, True):
            errors, value = validate_registration(invalid_body)
            self.assertEqual(len(errors), 1)
            self.assertIn("must be a JSON object", errors[0])
            self.assertIsNone(value)

    def test_rejects_name_lengths_out_of_bounds(self):
        # Too short (<2)
        errors, _ = validate_registration({**GOOD_PAYLOAD, "name": "A"})
        self.assertTrue(any("between 2 and 100 characters" in e for e in errors))

        # Too long (>100)
        errors, _ = validate_registration({**GOOD_PAYLOAD, "name": "A" * 101})
        self.assertTrue(any("between 2 and 100 characters" in e for e in errors))

    def test_rejects_invalid_email_formats(self):
        bad_emails = [
            "plainaddress",
            "@missingusername.com",
            "username@.com",
            "username@domain",
            "user with spaces@domain.com",
            "user@domain..com",
        ]
        for bad_email in bad_emails:
            errors, value = validate_registration({**GOOD_PAYLOAD, "email": bad_email})
            self.assertTrue(any("email format is invalid" in e for e in errors), f"Failed to reject: {bad_email}")
            self.assertIsNone(value)

    def test_rejects_unrecognised_department_or_interest(self):
        errors, _ = validate_registration({
            **GOOD_PAYLOAD,
            "department": "QuantumPhysics",
            "interest": "Astrology",
        })
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("department must be one of" in e for e in errors))
        self.assertTrue(any("interest must be one of" in e for e in errors))

    def test_ignores_non_string_values_gracefully(self):
        errors, _ = validate_registration({
            **GOOD_PAYLOAD,
            "name": 12345,
            "email": ["array@example.com"],
        })
        self.assertTrue(any("Missing required field: name" in e for e in errors))
        self.assertTrue(any("Missing required field: email" in e for e in errors))

    def test_accepts_valid_student_with_year_of_study(self):
        for year in YEARS_OF_STUDY:
            payload = {**GOOD_PAYLOAD, "yearOfStudy": year}
            errors, value = validate_registration(payload)
            self.assertEqual(errors, [])
            self.assertEqual(value["yearOfStudy"], year)

    # -------------------------------------------------------------------------
    # Mentor Validation Tests
    # -------------------------------------------------------------------------
    def test_accepts_valid_mentor_registration(self):
        errors, value = validate_registration(GOOD_MENTOR_PAYLOAD)
        self.assertEqual(errors, [])
        self.assertIsNotNone(value)
        self.assertEqual(value["registrationType"], "mentor")
        self.assertEqual(value["email"], "aaryan.mentor@bppimt.edu.in")
        self.assertEqual(value["name"], "Aaryan Kumar")
        self.assertEqual(value["currentRole"], "4th Year CSE & Cloud Lead")

    def test_reports_missing_fields_for_mentor_registration(self):
        errors, value = validate_registration({"registrationType": "mentor"})
        self.assertIsNone(value)
        self.assertEqual(len(errors), 6)
        self.assertTrue(any("name" in e for e in errors))
        self.assertTrue(any("email" in e for e in errors))
        self.assertTrue(any("currentRole" in e for e in errors))
        self.assertTrue(any("skills" in e for e in errors))
        self.assertTrue(any("mentorAreas" in e for e in errors))
        self.assertTrue(any("motivation" in e for e in errors))

    def test_rejects_mentor_motivation_too_short(self):
        payload = {**GOOD_MENTOR_PAYLOAD, "motivation": "Short"}
        errors, value = validate_registration(payload)
        self.assertIsNone(value)
        self.assertTrue(any("motivation statement must be between 10 and 1000 characters" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
