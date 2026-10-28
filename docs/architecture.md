# CloudPort System Architecture & Technical Specifications

> **Project:** CloudPort &bull; GDG on Campus BPPIMT Cloud Workshop  
> **Lead Engineer & Architect:** Aaryan Kumar  
> **Status:** Production-Ready  
> **Runtime:** Python 3.11 / 3.12 &bull; Google Cloud Functions (2nd Generation)  

---

## 1. Executive Summary & Objective

**CloudPort** is a production-grade, highly available, serverless event registration platform engineered for the **GDG on Campus BPPIMT Cloud Workshop**. It demonstrates modern Google Cloud Platform (GCP) architectural best practices:

1. **Client-Side:** Pure vanilla HTML5, CSS3, and JavaScript hosted as a static website on **Google Cloud Storage (GCS)**, eliminating server patching and idle compute costs.
2. **Serverless Compute:** An HTTP-triggered **Google Cloud Function (2nd Generation)** powered by Cloud Run and Knative, offering sub-second horizontal auto-scaling and concurrent execution.
3. **Database Layer:** **Google Cloud Firestore in Native mode**, providing globally distributed, high-throughput NoSQL document storage with ACID guarantees.
4. **Decoupled Messaging:** An asynchronous **Cloud Pub/Sub** event stream that triggers worker functions (such as confirmation emails via SendGrid) without blocking the client's HTTP request-response cycle.
5. **Least-Privilege Security:** Fine-grained IAM Service Accounts utilizing **Application Default Credentials (ADC)** with zero hardcoded credentials, complemented by anti-spam honeypot detection and deterministic SHA-256 idempotency.

---

## 2. High-Level Architecture Diagram

![Google Cloud Platform: Serverless Application Architecture](screenshots/system_architecture.png)

### Architectural Components:
1. **Client Tier:** Vanilla JS single-page web application (`index.html`, `style.css`, `script.js`) handling real-time input sanitization, RFC 5322 regex checks, and anti-spam honeypot verification.
2. **Static Edge Hosting:** Hosted on Google Cloud Storage and Firebase Hosting with multi-region CDN caching, achieving sub-100ms first paint times and 99.99% availability.
3. **Serverless Compute (Cloud Functions 2nd Gen):** HTTP-triggered Python 3.12 microservice running on Cloud Run, performing CORS origin whitelisting, payload validation, and computing deterministic document IDs.
4. **Database Layer (Cloud Firestore Native Mode):** Enterprise NoSQL document database (`registrations` collection) using deterministic SHA-256 email hashing as primary key for atomic duplicate prevention and UTC server timestamps.
5. **Decoupled Event Streaming (Cloud Pub/Sub):** Asynchronous messaging topic (`registration-created`) allowing decoupled downstream workers (e.g., SendGrid email microservice) to process notifications without slowing user HTTP responses.
6. **Observability Suite:** Full integration with Google Cloud Operations (Cloud Logging for structured JSON events and Cloud Monitoring for real-time alerting).

---

## 3. Request-Response Lifecycle Protocol

The following end-to-end protocol details the execution flow for attendee registration:

| Step | Lifecycle Phase | Participant | Operational Description |
|:---:|---|---|---|
| **1** | **Asset Loading** | Browser $\leftarrow$ Edge CDN | Client requests `/index.html`, `style.css`, and `script.js`. Assets are served compressed with global CDN edge caching. |
| **2** | **CORS Preflight** | Browser $\rightarrow$ Cloud Function | Browser issues `OPTIONS /register_user`. The function verifies the `Origin` header against `ALLOWED_ORIGINS` and responds with `204 No Content` and a 3600s cache window. |
| **3** | **Client Submission** | Browser $\rightarrow$ Cloud Function | User submits the registration form. Client-side JS validates fields, checks that the honeypot field is empty, and sends an HTTPS `POST` payload. |
| **4** | **Security Validation** | Cloud Function | The server validates schema boundaries, enforces RFC 5322 email syntax, rejects bot submissions silently if honeypot is populated, and computes `doc_id = SHA256(normalized_email)`. |
| **5A** | **Conflict Handling** | Cloud Function $\leftrightarrow$ Firestore | If a document with `doc_id` already exists, Firestore raises an `AlreadyExists` exception. The function traps this and immediately returns `409 Conflict` with `{ "ok": false, "code": "DUPLICATE_EMAIL" }`. |
| **5B** | **Atomic Persistence** | Cloud Function $\rightarrow$ Firestore | For new registrations, Firestore atomically commits the document with `created_at = firestore.SERVER_TIMESTAMP`. |
| **6** | **Async Decoupling** | Cloud Function $\rightarrow$ Pub/Sub | The function non-blockingly publishes a message to the `registration-created` Pub/Sub topic to trigger background email confirmation routines. |
| **7** | **Client Confirmation** | Cloud Function $\rightarrow$ Browser | Function responds with `201 Created` containing `{ "ok": true, "id": doc_id }`. The web app displays the Google-branded confirmation banner and renders the interactive digital admission ticket modal. |

---

## 4. Component Deep Dive

### 4.1 Frontend Client (`frontend/`)
- **Technology Stack:** Semantic HTML5, Vanilla CSS3 (custom CSS custom properties, zero CSS framework bloat), and modular Vanilla JavaScript (ES6+).
- **Hosting Strategy:** Hosted in a Google Cloud Storage bucket with `website` configuration enabled (`main_page_suffix = "index.html"`, `not_found_page = "index.html"`). All objects are given public read access (`roles/storage.objectViewer` to `allUsers`).
- **Dynamic Configuration:** Decoupled from hardcoded endpoints using `frontend/config.js` (`window.CLOUDPORT_CONFIG = { ENDPOINT: "..." }`) and supported by a runtime `localStorage` override modal for local or preview testing.
- **Client Validation & Accessibility:**
  - Semantic `<label for="...">` linking and ARIA attributes (`aria-required`, `aria-describedby`, `role="alert"`).
  - Immediate visual feedback on field blur and input events.
  - Interactive submit button state: disables during network transit and displays a spinning CSS loader to prevent accidental duplicate clicks.
  - Honeypot protection: An invisible field (`website`) traps automated spam scrapers. Genuine users never interact with it.

### 4.2 Backend Cloud Function (`backend/main.py`)
- **Runtime Environment:** Python 3.11 / 3.12 using Google Cloud Functions 2nd Generation (built atop Google Cloud Run).
- **HTTP Routing & CORS:**
  - Explicit handling for HTTP `OPTIONS` requests returning `204 No Content`, caching preflight checks for 3600 seconds (`Access-Control-Max-Age`).
  - Validates `Origin` header against `ALLOWED_ORIGINS` (comma-separated list, supporting `*` or specific origins like `https://storage.googleapis.com`).
  - Enforces `POST` method (rejecting others with `405 Method Not Allowed`) and `application/json` content type (rejecting non-JSON with `415 Unsupported Media Type`).
- **Validation Engine (`backend/validate.py`):**
  - Sanitizes and normalizes inputs (strips whitespace, forces lowercase email).
  - Enforces field length limits: `name` (2–100 chars), `email` (up to 254 chars with RFC 5322 regex disallowing double dots).
  - Strict whitelist checks against pre-approved academic departments (`DEPARTMENTS`) and workshop focus areas (`INTERESTS`).
- **Data Persistence:**
  - Computes a deterministic 32-character hexadecimal SHA-256 hash from the user's normalized email address.
  - Uses Firestore `document(doc_id).create(...)`. If the document already exists, Firestore raises `google.api_core.exceptions.AlreadyExists`, allowing the function to return a clean `409 Conflict` and prevent duplicate attendee records.
  - Attaches `firestore.SERVER_TIMESTAMP` so creation timestamps reflect exact Google server clocks, immune to client clock drift.
- **Error Obfuscation & Logging:**
  - Catches database or internal exceptions, logs structured JSON payloads with severity level `ERROR` to stdout for Cloud Logging ingestion, and returns a sanitized generic error message to the client (`500 Internal Server Error`). Internal database details, schemas, or stack traces are never exposed.

### 4.3 Database: Cloud Firestore Native (`(default)`)
- **Mode:** Native mode (not Datastore mode), offering rich real-time capabilities and native document collection hierarchies.
- **Data Collection:** `registrations`
- **Schema Definition:**
  ```json
  {
    "name": "string (2-100 characters)",
    "email": "string (lowercase, validated email)",
    "department": "string (CSE | IT | ECE | EE | ME | CE | BCA | MCA | MBA | Other)",
    "interest": "string (Cloud Infrastructure | Serverless | DevOps | Web Development | Mobile Development | Cybersecurity)",
    "createdAt": "Timestamp (server-generated UTC)",
    "source": "string (web_cloudport)"
  }
  ```

---

## 5. Security & Least-Privilege IAM Matrix

CloudPort implements zero-trust principles. No service account keys, passwords, or secrets are committed to version control or baked into container images. All services authenticate through Google Cloud runtime service accounts and Application Default Credentials (ADC).

| Principal (Identity) | Role Name | Resource Target | Justification / Purpose |
|---|---|---|---|
| **Public Users** (`allUsers`) | `roles/storage.objectViewer` | Website Bucket (`gs://[project]-cloudport-site`) | Allows visitors to download static web assets (`index.html`, `style.css`, etc.). |
| **Public Users** (`allUsers`) | `roles/cloudfunctions.invoker` | Registration Function (`cloudport-register`) | Allows anonymous workshop attendees to submit the registration form. |
| **`cloudport-register-sa`** | `roles/datastore.user` | Project Firestore Database | Enables the function to read/write attendee documents in `registrations`. |
| **`cloudport-register-sa`** | `roles/pubsub.publisher` | Topic `registration-created` | Enables publishing asynchronous registration events for downstream workers. |
| **`cloudport-confirm-sa`** | `roles/secretmanager.secretAccessor` | Secret `cloudport-sendgrid-api-key` | Allows the email worker to fetch the SendGrid API key securely at runtime. |
| **`cloudport-confirm-sa`** | `roles/eventarc.eventReceiver` | Project / Region | Allows Eventarc to route Pub/Sub messages to the Cloud Run trigger. |
| **`cloudport-confirm-sa`** | `roles/run.invoker` | Cloud Run Service `cloudport-send-confirmation` | Allows Eventarc to invoke the confirmation email function. |

---

## 6. Observability & Reliability Architecture

CloudPort incorporates continuous monitoring and alerting:

1. **Structured Cloud Logging:**
   All function logs are output as JSON strings containing `severity`, `message`, and contextual metadata (`id`, `email`, `error`). Google Cloud Logging automatically extracts these fields, enabling targeted log queries:
   ```sql
   resource.type="cloud_run_revision"
   resource.labels.service_name="cloudport-register"
   severity>=ERROR
   ```

2. **Log-Based Metrics:**
   A custom metric (`cloudport_function_errors`) tracks error counts across revisions.

3. **Cloud Monitoring Alert Policies:**
   - **5xx HTTP Errors:** Alerts when the registration function returns any `5xx` status code over a 5-minute rolling window.
   - **Error Logs:** Alerts on unhandled exceptions in the application layer.

---

## 7. Cost & Free Tier Optimization

CloudPort is engineered to run at **$0.00 / month** under Google Cloud's permanent Free Tier allocations:

| GCP Service | Free Tier Monthly Allowance | CloudPort Expected Utilization | Est. Cost |
|---|---|---|---|
| **Cloud Storage** | 5 GB standard storage, 50,000 Class B read requests | ~10 MB static assets, ~5,000 views | $0.00 |
| **Cloud Functions (2nd Gen)** | 2 million invocations, 400,000 GB-seconds compute | ~500–2,000 invocations | $0.00 |
| **Cloud Firestore** | 1 GB storage, 50,000 reads/day, 20,000 writes/day | < 500 documents (~100 KB total) | $0.00 |
| **Cloud Pub/Sub** | 10 GB messages / month | < 5 MB message volume | $0.00 |
| **Cloud Logging / Monitoring** | 50 GB log ingestion / month | < 50 MB log volume | $0.00 |
