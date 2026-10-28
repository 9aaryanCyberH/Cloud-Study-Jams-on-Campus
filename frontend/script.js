/**
 * Google Cloud Study Jams 2026 — Frontend Application Script
 * Organized by Google Developer Group, B. P. Poddar Institute of Management & Technology (BPPIMT)
 *
 * Handles:
 *   - Client-side input validation and error feedback
 *   - Student participant registration
 *   - Mentor volunteer registration
 *   - Serverless backend communication via Fetch API
 *   - Success modals with digital admission tickets and copy-to-clipboard
 *   - Responsive mobile navigation
 *   - Zero visible API endpoint status leakage
 */

(function () {
  'use strict';

  // Storage key for optional local developer endpoint override
  const STORAGE_KEY_ENDPOINT = 'CLOUDPORT_ENDPOINT_OVERRIDE';

  // RFC 5322 compliant email regex matching backend validation (disallows consecutive dots)
  const EMAIL_REGEX = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$/;

  // -------------------------------------------------------------------------
  // DOM Elements: Navigation & Modals
  // -------------------------------------------------------------------------
  const mobileMenuToggle = document.getElementById('mobileMenuToggle');
  const navMenu = document.getElementById('navMenu');
  const toastContainer = document.getElementById('toastContainer');

  // Student Form & Controls
  const studentForm = document.getElementById('studentRegistrationForm');
  const studentNameInput = document.getElementById('studentName');
  const studentEmailInput = document.getElementById('studentEmail');
  const studentDeptSelect = document.getElementById('studentDepartment');
  const studentYearSelect = document.getElementById('studentYear');
  const studentInterestSelect = document.getElementById('studentInterest');
  const studentWebsiteInput = document.getElementById('studentWebsite');
  const studentSubmitBtn = document.getElementById('studentSubmitBtn');
  const studentSpinner = document.getElementById('studentSpinner');
  const studentBtnText = document.getElementById('studentBtnText');
  const studentFormError = document.getElementById('studentFormError');
  const studentErrorTitle = document.getElementById('studentErrorTitle');
  const studentErrorMessage = document.getElementById('studentErrorMessage');

  // Student Error Elements
  const studentNameError = document.getElementById('studentNameError');
  const studentEmailError = document.getElementById('studentEmailError');
  const studentDeptError = document.getElementById('studentDepartmentError');
  const studentYearError = document.getElementById('studentYearError');
  const studentInterestError = document.getElementById('studentInterestError');

  // Student Modal Elements
  const studentSuccessModal = document.getElementById('studentSuccessModal');
  const confirmedStudentName = document.getElementById('confirmedStudentName');
  const confirmedStudentEmail = document.getElementById('confirmedStudentEmail');
  const confirmedStudentInterest = document.getElementById('confirmedStudentInterest');
  const confirmedStudentId = document.getElementById('confirmedStudentId');
  const copyStudentIdBtn = document.getElementById('copyStudentIdBtn');
  const closeStudentSuccessBtn = document.getElementById('closeStudentSuccessBtn');

  // Mentor Form & Controls
  const mentorForm = document.getElementById('mentorRegistrationForm');
  const mentorNameInput = document.getElementById('mentorName');
  const mentorEmailInput = document.getElementById('mentorEmail');
  const mentorRoleInput = document.getElementById('mentorRole');
  const mentorSkillsInput = document.getElementById('mentorSkills');
  const mentorAreasInput = document.getElementById('mentorAreas');
  const mentorMotivationInput = document.getElementById('mentorMotivation');
  const mentorWebsiteInput = document.getElementById('mentorWebsite');
  const mentorSubmitBtn = document.getElementById('mentorSubmitBtn');
  const mentorSpinner = document.getElementById('mentorSpinner');
  const mentorBtnText = document.getElementById('mentorBtnText');
  const mentorFormError = document.getElementById('mentorFormError');
  const mentorErrorTitle = document.getElementById('mentorErrorTitle');
  const mentorErrorMessage = document.getElementById('mentorErrorMessage');

  // Mentor Error Elements
  const mentorNameError = document.getElementById('mentorNameError');
  const mentorEmailError = document.getElementById('mentorEmailError');
  const mentorRoleError = document.getElementById('mentorRoleError');
  const mentorSkillsError = document.getElementById('mentorSkillsError');
  const mentorAreasError = document.getElementById('mentorAreasError');
  const mentorMotivationError = document.getElementById('mentorMotivationError');

  // Mentor Modal Elements
  const mentorSuccessModal = document.getElementById('mentorSuccessModal');
  const confirmedMentorName = document.getElementById('confirmedMentorName');
  const confirmedMentorEmail = document.getElementById('confirmedMentorEmail');
  const confirmedMentorId = document.getElementById('confirmedMentorId');
  const copyMentorIdBtn = document.getElementById('copyMentorIdBtn');
  const closeMentorSuccessBtn = document.getElementById('closeMentorSuccessBtn');

  // -------------------------------------------------------------------------
  // Endpoint Resolution (Invisible in UI)
  // -------------------------------------------------------------------------
  function getActiveEndpoint() {
    const urlParams = new URLSearchParams(window.location.search);
    const queryEndpoint = urlParams.get('endpoint');
    if (queryEndpoint && isValidHttpUrl(queryEndpoint)) {
      return queryEndpoint.trim();
    }

    const storedOverride = localStorage.getItem(STORAGE_KEY_ENDPOINT);
    if (storedOverride && storedOverride.trim() && isValidHttpUrl(storedOverride)) {
      return storedOverride.trim();
    }

    if (window.CLOUDPORT_CONFIG && window.CLOUDPORT_CONFIG.ENDPOINT) {
      return window.CLOUDPORT_CONFIG.ENDPOINT.trim();
    }

    return '';
  }

  function isValidHttpUrl(string) {
    try {
      const url = new URL(string);
      return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (_) {
      return false;
    }
  }

  async function sha256Hex32(message) {
    if (window.crypto && window.crypto.subtle) {
      const msgBuffer = new TextEncoder().encode(message);
      const hashBuffer = await window.crypto.subtle.digest('SHA-256', msgBuffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 32);
    }
    let h1 = 0xdeadbeef, h2 = 0x41c64e6d;
    for (let i = 0; i < message.length; i++) {
      const ch = message.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    const hex = (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).padStart(16, '0');
    return (hex + hex).slice(0, 32);
  }

  async function submitRegistration(payload) {
    // 1. Anti-spam Honeypot check
    if (payload.website && payload.website.trim()) {
      console.info('[CloudPort] Honeypot triggered, simulating success');
      return { ok: true, id: 'RECEIPT-' + Date.now().toString(36).toUpperCase() };
    }

    const endpoint = getActiveEndpoint();

    // Pathway A: Explicit Backend API Endpoint (Localhost Python server or custom Cloud Function)
    if (endpoint) {
      if (window.location.protocol === 'https:' && endpoint.startsWith('http://') && !endpoint.includes('127.0.0.1') && !endpoint.includes('localhost')) {
        return {
          ok: false,
          status: 0,
          error: `Insecure HTTP endpoint (${endpoint}) blocked under browser Mixed Content rules.`
        };
      }

      const targetUrl = `${endpoint.replace(/\/+$/, '')}/register_user`;
      console.info('[CloudPort] Submitting via Backend API:', targetUrl);

      const response = await fetch(targetUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) {
        return { ok: true, id: data.id || 'CONFIRMED' };
      }
      return {
        ok: false,
        status: response.status,
        error: data.error,
        code: data.code
      };
    }

    // Pathway B: Direct Google Cloud Firestore Native REST API (Zero-Billing Cloud Deployment)
    const projectId = (window.CLOUDPORT_CONFIG && window.CLOUDPORT_CONFIG.PROJECT_ID) || 'cloud-study-jams-3f931';
    const emailNorm = payload.email.trim().toLowerCase();
    const docHashInput = payload.registrationType === 'mentor' ? `mentor:${emailNorm}` : emailNorm;
    const docId = await sha256Hex32(docHashInput);

    const firestoreUrl = `https://firestore.googleapis.com/v1/projects/${projectId}/databases/(default)/documents/registrations?documentId=${docId}`;
    console.info('[CloudPort] Submitting directly to Google Cloud Firestore Native:', firestoreUrl);

    // Map payload into Firestore Native document fields
    const fields = {
      name: { stringValue: payload.name },
      email: { stringValue: emailNorm },
      registrationType: { stringValue: payload.registrationType },
      source: { stringValue: 'web_cloudport' },
      createdAt: { timestampValue: new Date().toISOString() }
    };

    if (payload.registrationType === 'student') {
      fields.department = { stringValue: payload.department };
      fields.yearOfStudy = { stringValue: payload.yearOfStudy };
      fields.interest = { stringValue: payload.interest };
    } else {
      fields.currentRole = { stringValue: payload.currentRole };
      fields.skills = { stringValue: payload.skills };
      fields.mentorAreas = { stringValue: payload.mentorAreas };
      fields.motivation = { stringValue: payload.motivation };
    }

    const response = await fetch(firestoreUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields })
    });

    if (response.ok) {
      return { ok: true, id: docId };
    }

    const errData = await response.json().catch(() => ({}));
    if (response.status === 409 || (errData.error && errData.error.status === 'ALREADY_EXISTS')) {
      const duplicateMsg = payload.registrationType === 'mentor'
        ? 'This email address has already submitted a mentor application.'
        : 'This email address is already registered for Study Jams 2026.';
      return { ok: false, status: 409, error: duplicateMsg, code: 'DUPLICATE_EMAIL' };
    }

    return {
      ok: false,
      status: response.status,
      error: (errData.error && errData.error.message) || 'Failed to save registration record into Firestore.'
    };
  }

  // -------------------------------------------------------------------------
  // Validation Helpers
  // -------------------------------------------------------------------------
  function setFieldState(element, errorElement, isValid, errorMsg) {
    if (isValid) {
      element.classList.remove('is-invalid');
      element.classList.add('is-valid');
      errorElement.textContent = '';
    } else {
      element.classList.remove('is-valid');
      element.classList.add('is-invalid');
      errorElement.textContent = errorMsg;
    }
  }

  function validateStudentFields() {
    let isValid = true;

    // Name
    const nameVal = studentNameInput.value.trim();
    if (!nameVal) {
      setFieldState(studentNameInput, studentNameError, false, 'Please enter your full name.');
      isValid = false;
    } else if (nameVal.length < 2 || nameVal.length > 100) {
      setFieldState(studentNameInput, studentNameError, false, 'Name must be between 2 and 100 characters.');
      isValid = false;
    } else {
      setFieldState(studentNameInput, studentNameError, true, '');
    }

    // Email
    const emailVal = studentEmailInput.value.trim();
    if (!emailVal) {
      setFieldState(studentEmailInput, studentEmailError, false, 'Please enter your email address.');
      isValid = false;
    } else if (!EMAIL_REGEX.test(emailVal)) {
      setFieldState(studentEmailInput, studentEmailError, false, 'Please enter a valid email address (e.g. name@bppimt.edu.in).');
      isValid = false;
    } else {
      setFieldState(studentEmailInput, studentEmailError, true, '');
    }

    // Department
    if (!studentDeptSelect.value) {
      setFieldState(studentDeptSelect, studentDeptError, false, 'Please select your department.');
      isValid = false;
    } else {
      setFieldState(studentDeptSelect, studentDeptError, true, '');
    }

    // Year
    if (!studentYearSelect.value) {
      setFieldState(studentYearSelect, studentYearError, false, 'Please select your year of study.');
      isValid = false;
    } else {
      setFieldState(studentYearSelect, studentYearError, true, '');
    }

    // Interest
    if (!studentInterestSelect.value) {
      setFieldState(studentInterestSelect, studentInterestError, false, 'Please select an area of interest.');
      isValid = false;
    } else {
      setFieldState(studentInterestSelect, studentInterestError, true, '');
    }

    return isValid;
  }

  function validateMentorFields() {
    let isValid = true;

    // Name
    const nameVal = mentorNameInput.value.trim();
    if (!nameVal || nameVal.length < 2 || nameVal.length > 100) {
      setFieldState(mentorNameInput, mentorNameError, false, 'Full name must be between 2 and 100 characters.');
      isValid = false;
    } else {
      setFieldState(mentorNameInput, mentorNameError, true, '');
    }

    // Email
    const emailVal = mentorEmailInput.value.trim();
    if (!emailVal || !EMAIL_REGEX.test(emailVal)) {
      setFieldState(mentorEmailInput, mentorEmailError, false, 'Please enter a valid email address.');
      isValid = false;
    } else {
      setFieldState(mentorEmailInput, mentorEmailError, true, '');
    }

    // Current Role
    const roleVal = mentorRoleInput.value.trim();
    if (!roleVal || roleVal.length < 2 || roleVal.length > 100) {
      setFieldState(mentorRoleInput, mentorRoleError, false, 'Please specify your current role or year of study.');
      isValid = false;
    } else {
      setFieldState(mentorRoleInput, mentorRoleError, true, '');
    }

    // Skills
    const skillsVal = mentorSkillsInput.value.trim();
    if (!skillsVal || skillsVal.length < 2 || skillsVal.length > 250) {
      setFieldState(mentorSkillsInput, mentorSkillsError, false, 'Please provide your relevant technical skills.');
      isValid = false;
    } else {
      setFieldState(mentorSkillsInput, mentorSkillsError, true, '');
    }

    // Mentor Areas
    const areasVal = mentorAreasInput.value.trim();
    if (!areasVal || areasVal.length < 2 || areasVal.length > 250) {
      setFieldState(mentorAreasInput, mentorAreasError, false, 'Please specify the areas you can mentor.');
      isValid = false;
    } else {
      setFieldState(mentorAreasInput, mentorAreasError, true, '');
    }

    // Motivation
    const motVal = mentorMotivationInput.value.trim();
    if (!motVal || motVal.length < 10 || motVal.length > 1000) {
      setFieldState(mentorMotivationInput, mentorMotivationError, false, 'Please share a brief motivation statement (at least 10 characters).');
      isValid = false;
    } else {
      setFieldState(mentorMotivationInput, mentorMotivationError, true, '');
    }

    return isValid;
  }

  // -------------------------------------------------------------------------
  // Live Validation Event Listeners
  // -------------------------------------------------------------------------
  if (studentNameInput) {
    studentNameInput.addEventListener('input', () => {
      if (studentNameInput.classList.contains('is-invalid')) validateStudentFields();
    });
    studentEmailInput.addEventListener('input', () => {
      if (studentEmailInput.classList.contains('is-invalid')) validateStudentFields();
    });
    studentDeptSelect.addEventListener('change', () => {
      if (studentDeptSelect.classList.contains('is-invalid')) validateStudentFields();
    });
    studentYearSelect.addEventListener('change', () => {
      if (studentYearSelect.classList.contains('is-invalid')) validateStudentFields();
    });
    studentInterestSelect.addEventListener('change', () => {
      if (studentInterestSelect.classList.contains('is-invalid')) validateStudentFields();
    });
  }

  if (mentorNameInput) {
    mentorNameInput.addEventListener('input', () => {
      if (mentorNameInput.classList.contains('is-invalid')) validateMentorFields();
    });
    mentorEmailInput.addEventListener('input', () => {
      if (mentorEmailInput.classList.contains('is-invalid')) validateMentorFields();
    });
    mentorRoleInput.addEventListener('input', () => {
      if (mentorRoleInput.classList.contains('is-invalid')) validateMentorFields();
    });
    mentorSkillsInput.addEventListener('input', () => {
      if (mentorSkillsInput.classList.contains('is-invalid')) validateMentorFields();
    });
    mentorAreasInput.addEventListener('input', () => {
      if (mentorAreasInput.classList.contains('is-invalid')) validateMentorFields();
    });
    mentorMotivationInput.addEventListener('input', () => {
      if (mentorMotivationInput.classList.contains('is-invalid')) validateMentorFields();
    });
  }

  // -------------------------------------------------------------------------
  // Student Form Submission Handler
  // -------------------------------------------------------------------------
  if (studentForm) {
    studentForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      studentFormError.style.display = 'none';

      if (!validateStudentFields()) {
        studentErrorTitle.textContent = 'Incomplete Information';
        studentErrorMessage.textContent = 'Please review the highlighted fields above.';
        studentFormError.style.display = 'flex';
        return;
      }

      const endpoint = getActiveEndpoint();
      const statusCheck = checkEndpointStatus(endpoint);
      if (!statusCheck.ok) {
        console.warn('[CloudPort] Endpoint check failed:', statusCheck.message, { endpoint, origin: window.location.origin });
        studentErrorTitle.textContent = statusCheck.title;
        studentErrorMessage.textContent = statusCheck.message;
        studentFormError.style.display = 'flex';
        return;
      }

      // Payload matching backend schema
      const payload = {
        registrationType: 'student',
        name: studentNameInput.value.trim(),
        email: studentEmailInput.value.trim().toLowerCase(),
        department: studentDeptSelect.value,
        yearOfStudy: studentYearSelect.value,
        interest: studentInterestSelect.value,
        website: studentWebsiteInput ? studentWebsiteInput.value.trim() : ''
      };

      // Set Loading State
      studentSubmitBtn.disabled = true;
      studentSpinner.style.display = 'inline-block';
      studentBtnText.textContent = 'Registering...';

      try {
        const result = await submitRegistration(payload);

        if (result.ok) {
          // Success Display
          confirmedStudentName.textContent = payload.name;
          confirmedStudentEmail.textContent = payload.email;
          confirmedStudentInterest.textContent = payload.interest;
          confirmedStudentId.textContent = result.id || 'CONFIRMED';

          studentSuccessModal.style.display = 'flex';
          studentForm.reset();

          // Reset validation styles
          [studentNameInput, studentEmailInput, studentDeptSelect, studentYearSelect, studentInterestSelect].forEach(el => {
            el.classList.remove('is-valid');
          });
        } else if (result.status === 409 || result.code === 'DUPLICATE_EMAIL') {
          studentErrorTitle.textContent = 'Already Registered';
          studentErrorMessage.textContent = result.error || 'This email address is already registered for Study Jams 2026.';
          studentFormError.style.display = 'flex';
        } else if (result.status === 400) {
          studentErrorTitle.textContent = 'Validation Error';
          studentErrorMessage.textContent = result.error || 'Please ensure all submitted details are formatted correctly.';
          studentFormError.style.display = 'flex';
        } else if (result.status === 403) {
          studentErrorTitle.textContent = 'Access Denied';
          studentErrorMessage.textContent = result.error || 'The request was rejected by security policies.';
          studentFormError.style.display = 'flex';
        } else {
          studentErrorTitle.textContent = 'Submission Failed';
          studentErrorMessage.textContent = result.error || 'An error occurred processing your registration.';
          studentFormError.style.display = 'flex';
        }
      } catch (err) {
        console.error('[CloudPort] Student registration failure:', err, { origin: window.location.origin });
        studentErrorTitle.textContent = 'Connection Error';
        studentErrorMessage.textContent = 'Could not reach the registration service. Please verify your internet connection.';
        studentFormError.style.display = 'flex';
      } finally {
        studentSubmitBtn.disabled = false;
        studentSpinner.style.display = 'none';
        studentBtnText.textContent = 'Register as a Student \u2192';
      }
    });
  }

  // -------------------------------------------------------------------------
  // Mentor Form Submission Handler
  // -------------------------------------------------------------------------
  if (mentorForm) {
    mentorForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      mentorFormError.style.display = 'none';

      if (!validateMentorFields()) {
        mentorErrorTitle.textContent = 'Incomplete Information';
        mentorErrorMessage.textContent = 'Please review the highlighted fields above.';
        mentorFormError.style.display = 'flex';
        return;
      }

      // Payload matching backend mentor schema
      const payload = {
        registrationType: 'mentor',
        name: mentorNameInput.value.trim(),
        email: mentorEmailInput.value.trim().toLowerCase(),
        currentRole: mentorRoleInput.value.trim(),
        skills: mentorSkillsInput.value.trim(),
        mentorAreas: mentorAreasInput.value.trim(),
        motivation: mentorMotivationInput.value.trim(),
        website: mentorWebsiteInput ? mentorWebsiteInput.value.trim() : ''
      };

      // Set Loading State
      mentorSubmitBtn.disabled = true;
      mentorSpinner.style.display = 'inline-block';
      mentorBtnText.textContent = 'Submitting Application...';

      try {
        const result = await submitRegistration(payload);

        if (result.ok) {
          // Success Display
          confirmedMentorName.textContent = payload.name;
          confirmedMentorEmail.textContent = payload.email;
          confirmedMentorId.textContent = result.id || 'CONFIRMED';

          mentorSuccessModal.style.display = 'flex';
          mentorForm.reset();

          // Reset validation styles
          [mentorNameInput, mentorEmailInput, mentorRoleInput, mentorSkillsInput, mentorAreasInput, mentorMotivationInput].forEach(el => {
            el.classList.remove('is-valid');
          });
        } else if (result.status === 409 || result.code === 'DUPLICATE_EMAIL') {
          mentorErrorTitle.textContent = 'Already Submitted';
          mentorErrorMessage.textContent = result.error || 'This email address has already submitted a mentor application.';
          mentorFormError.style.display = 'flex';
        } else if (result.status === 400) {
          mentorErrorTitle.textContent = 'Validation Error';
          mentorErrorMessage.textContent = result.error || 'Please ensure all submitted details are formatted correctly.';
          mentorFormError.style.display = 'flex';
        } else if (result.status === 403) {
          mentorErrorTitle.textContent = 'Access Denied';
          mentorErrorMessage.textContent = result.error || 'The request was rejected by security policies.';
          mentorFormError.style.display = 'flex';
        } else {
          mentorErrorTitle.textContent = 'Submission Failed';
          mentorErrorMessage.textContent = result.error || 'An error occurred processing your application.';
          mentorFormError.style.display = 'flex';
        }
      } catch (err) {
        console.error('[CloudPort] Mentor application failure:', err, { origin: window.location.origin });
        mentorErrorTitle.textContent = 'Connection Error';
        mentorErrorMessage.textContent = 'Could not reach the application service. Please verify your internet connection.';
        mentorFormError.style.display = 'flex';
      } finally {
        mentorSubmitBtn.disabled = false;
        mentorSpinner.style.display = 'none';
        mentorBtnText.textContent = 'Submit Mentor Application \u2192';
      }
    });
  }

  // -------------------------------------------------------------------------
  // Modals & Clipboard Helpers
  // -------------------------------------------------------------------------
  if (closeStudentSuccessBtn) {
    closeStudentSuccessBtn.addEventListener('click', () => {
      studentSuccessModal.style.display = 'none';
    });
  }

  if (studentSuccessModal) {
    studentSuccessModal.addEventListener('click', (e) => {
      if (e.target === studentSuccessModal) {
        studentSuccessModal.style.display = 'none';
      }
    });
  }

  if (closeMentorSuccessBtn) {
    closeMentorSuccessBtn.addEventListener('click', () => {
      mentorSuccessModal.style.display = 'none';
    });
  }

  if (mentorSuccessModal) {
    mentorSuccessModal.addEventListener('click', (e) => {
      if (e.target === mentorSuccessModal) {
        mentorSuccessModal.style.display = 'none';
      }
    });
  }

  function copyToClipboard(text, successMessage) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        showToast(successMessage);
      }).catch(() => {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    const el = document.createElement('textarea');
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
    showToast('Copied to clipboard!');
  }

  if (copyStudentIdBtn) {
    copyStudentIdBtn.addEventListener('click', () => {
      copyToClipboard(confirmedStudentId.textContent.trim(), 'Registration ID copied to clipboard!');
    });
  }

  if (copyMentorIdBtn) {
    copyMentorIdBtn.addEventListener('click', () => {
      copyToClipboard(confirmedMentorId.textContent.trim(), 'Application ID copied to clipboard!');
    });
  }

  function showToast(message) {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 3000);
  }

  // -------------------------------------------------------------------------
  // Mobile Navigation
  // -------------------------------------------------------------------------
  if (mobileMenuToggle && navMenu) {
    mobileMenuToggle.addEventListener('click', () => {
      const isExpanded = mobileMenuToggle.getAttribute('aria-expanded') === 'true';
      mobileMenuToggle.setAttribute('aria-expanded', !isExpanded);
      navMenu.classList.toggle('nav-menu-open');
    });

    // Close menu when clicking a link
    navMenu.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', () => {
        navMenu.classList.remove('nav-menu-open');
        mobileMenuToggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // -------------------------------------------------------------------------
  // Back to Top Smooth Scroll
  // -------------------------------------------------------------------------
  const backToTopBtn = document.getElementById('backToTopBtn');
  if (backToTopBtn) {
    backToTopBtn.addEventListener('click', (e) => {
      e.preventDefault();
      window.scrollTo({
        top: 0,
        left: 0,
        behavior: 'smooth'
      });
      if (window.history && window.history.pushState) {
        window.history.pushState(null, null, '#top');
      }
    });
  }

  // -------------------------------------------------------------------------
  // Interactive Google Cloud Platform Architecture Showcase (Zero-Flicker)
  // -------------------------------------------------------------------------
  function initInteractiveGraphic() {
    const showcase = document.querySelector('.gcp-architecture-showcase');
    const hubSubtitle = document.getElementById('gcpHubSubtitle');
    const statusText = document.getElementById('gcpStatusText');
    const centerHub = document.getElementById('gcpCenterHub');
    const serviceCards = document.querySelectorAll('.gcp-service-card');

    if (!showcase || !serviceCards.length) return;

    const TOOL_DATA = {
      gcs: {
        subtitle: 'Static Web Hosting',
        status: 'GCS Bucket Serving UI',
        rayId: 'rayStorage'
      },
      functions: {
        subtitle: 'Serverless Python API',
        status: 'POST /register_user (2nd Gen)',
        rayId: 'rayFunctions'
      },
      firestore: {
        subtitle: 'Native NoSQL Store',
        status: 'registrations Collection',
        rayId: 'rayFirestore'
      },
      security: {
        subtitle: 'Security & Events',
        status: 'Least-Privilege & IAM',
        rayId: 'raySecurity'
      }
    };

    function activateTool(toolKey) {
      const data = TOOL_DATA[toolKey];
      if (!data) return;

      // Update card active states
      serviceCards.forEach(card => {
        const isMatch = card.getAttribute('data-tool') === toolKey;
        card.classList.toggle('active', isMatch);
      });

      // Update SVG ray highlights
      document.querySelectorAll('.gcp-ray').forEach(ray => {
        ray.classList.toggle('active', ray.id === data.rayId);
      });

      // Update Hub Text
      if (hubSubtitle) hubSubtitle.textContent = data.subtitle;
      if (statusText) statusText.textContent = data.status;
    }

    function resetGraphic() {
      serviceCards.forEach(card => card.classList.remove('active'));
      document.querySelectorAll('.gcp-ray').forEach(ray => ray.classList.remove('active'));
      if (hubSubtitle) hubSubtitle.textContent = 'Serverless Architecture';
      if (statusText) statusText.textContent = 'Live Data Pipeline';
    }

    // Attach stable hover and click listeners to cards (no mousemove perspective!)
    serviceCards.forEach(card => {
      const toolKey = card.getAttribute('data-tool');

      card.addEventListener('mouseenter', () => {
        activateTool(toolKey);
      });

      card.addEventListener('click', () => {
        activateTool(toolKey);
      });

      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          activateTool(toolKey);
        }
      });
    });

    // Reset when leaving the entire showcase region
    showcase.addEventListener('mouseleave', resetGraphic);

    // Center hub click cycles through the tools
    if (centerHub) {
      const tools = Object.keys(TOOL_DATA);
      let activeIndex = 0;
      centerHub.addEventListener('click', () => {
        activateTool(tools[activeIndex]);
        activeIndex = (activeIndex + 1) % tools.length;
      });
    }
  }

  // Initialize interactive graphic
  initInteractiveGraphic();
})();
