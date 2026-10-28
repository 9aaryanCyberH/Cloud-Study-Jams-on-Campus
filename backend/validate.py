"""Pure validation helpers for Google Cloud Study Jams 2026 registration (GDG on Campus BPPIMT).

Zero GCP imports for high-speed offline unit testing.
Supports both student participant and mentor volunteer registration schemas.
"""
import re

# Supported departments for GDG BPPIMT students
DEPARTMENTS = [
    "CSE",
    "IT",
    "ECE",
    "EE",
    "ME",
    "CE",
    "BCA",
    "MCA",
    "MBA",
    "Other",
]

# Supported years of study
YEARS_OF_STUDY = [
    "1st Year",
    "2nd Year",
    "3rd Year",
    "4th Year",
    "Postgraduate",
    "Other",
]

# Supported focus areas and curriculum tracks
INTERESTS = [
    "Cloud Infrastructure",
    "Serverless",
    "DevOps",
    "Web Development",
    "Mobile Development",
    "Cybersecurity",
    "Data & Storage",
    "Cloud Fundamentals",
]

# RFC 5322 compliant simplified email regex (disallows consecutive dots)
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$")


def _clean(value):
    """Strip string whitespace or return empty string for non-string values."""
    return value.strip() if isinstance(value, str) else ""


def validate_student_registration(body):
    """Validate and normalise a student participant registration payload.

    Args:
        body: Decoded JSON request payload dict.

    Returns:
        tuple (errors, value):
          - errors: list of error strings (empty if valid).
          - value: normalised dictionary of sanitized inputs, or None if errors exist.
    """
    name = _clean(body.get("name"))
    email = _clean(body.get("email")).lower()
    department = _clean(body.get("department"))
    interest = _clean(body.get("interest"))
    year_of_study = _clean(body.get("yearOfStudy") or body.get("year"))

    errors = []

    # Required field presence checks
    for field, val in (
        ("name", name),
        ("email", email),
        ("department", department),
        ("interest", interest),
    ):
        if not val:
            errors.append(f"Missing required field: {field}")

    # Format and constraint validations
    if name and not (2 <= len(name) <= 100):
        errors.append("name must be between 2 and 100 characters")

    if email:
        if len(email) > 254:
            errors.append("email must not exceed 254 characters")
        elif not _EMAIL_RE.match(email):
            errors.append("email format is invalid")

    if department and department not in DEPARTMENTS:
        errors.append(f"department must be one of: {', '.join(DEPARTMENTS)}")

    if interest and interest not in INTERESTS:
        errors.append(f"interest must be one of: {', '.join(INTERESTS)}")

    if year_of_study and year_of_study not in YEARS_OF_STUDY and not (2 <= len(year_of_study) <= 50):
        errors.append(f"yearOfStudy must be one of: {', '.join(YEARS_OF_STUDY)}")

    if errors:
        return errors, None

    result = {
        "registrationType": "student",
        "name": name,
        "email": email,
        "department": department,
        "interest": interest,
    }
    if year_of_study:
        result["yearOfStudy"] = year_of_study

    return [], result


def validate_mentor_registration(body):
    """Validate and normalise a mentor volunteer application payload.

    Args:
        body: Decoded JSON request payload dict.

    Returns:
        tuple (errors, value):
          - errors: list of error strings (empty if valid).
          - value: normalised dictionary of sanitized inputs, or None if errors exist.
    """
    name = _clean(body.get("name"))
    email = _clean(body.get("email")).lower()
    current_role = _clean(body.get("currentRole") or body.get("role"))
    skills = _clean(body.get("skills"))
    mentor_areas = _clean(body.get("mentorAreas") or body.get("areas"))
    motivation = _clean(body.get("motivation") or body.get("statement"))

    errors = []

    # Required field presence checks
    for field, val in (
        ("name", name),
        ("email", email),
        ("currentRole", current_role),
        ("skills", skills),
        ("mentorAreas", mentor_areas),
        ("motivation", motivation),
    ):
        if not val:
            errors.append(f"Missing required field: {field}")

    # Format and constraint validations
    if name and not (2 <= len(name) <= 100):
        errors.append("name must be between 2 and 100 characters")

    if email:
        if len(email) > 254:
            errors.append("email must not exceed 254 characters")
        elif not _EMAIL_RE.match(email):
            errors.append("email format is invalid")

    if current_role and not (2 <= len(current_role) <= 100):
        errors.append("currentRole must be between 2 and 100 characters")

    if skills and not (2 <= len(skills) <= 250):
        errors.append("skills must be between 2 and 250 characters")

    if mentor_areas and not (2 <= len(mentor_areas) <= 250):
        errors.append("mentorAreas must be between 2 and 250 characters")

    if motivation and not (10 <= len(motivation) <= 1000):
        errors.append("motivation statement must be between 10 and 1000 characters")

    if errors:
        return errors, None

    return [], {
        "registrationType": "mentor",
        "name": name,
        "email": email,
        "currentRole": current_role,
        "skills": skills,
        "mentorAreas": mentor_areas,
        "motivation": motivation,
    }


def validate_registration(body):
    """Dispatch and validate a registration payload based on registrationType.

    Defaults to student participant schema for backward compatibility.
    """
    if not isinstance(body, dict):
        return ["Request body must be a JSON object"], None

    reg_type = _clean(body.get("registrationType") or body.get("type")).lower()
    if reg_type == "mentor":
        return validate_mentor_registration(body)
    return validate_student_registration(body)
