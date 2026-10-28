/**
 * CloudPort Frontend Runtime Configuration
 *
 * Configures the backend Cloud Function API endpoint and Google Cloud Firestore project.
 *
 * Execution Pathways:
 *   1. Local Development (localhost / 127.0.0.1):
 *      Routes to the local Python backend API (`http://127.0.0.1:8080/register_user`).
 *   2. Custom Cloud Function:
 *      Can be set via URL param (`?endpoint=https://...`) or `localStorage.setItem('CLOUDPORT_API_ENDPOINT', '...')`.
 *   3. Deployed Cloud Web App (https://cloud-study-jams-3f931.web.app):
 *      Routes directly to Google Cloud Firestore Native REST API on project `cloud-study-jams-3f931` (Free Tier).
 */
(function () {
  const isLocalHost = Boolean(
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname === '[::1]'
  );

  window.CLOUDPORT_CONFIG = {
    // Target Google Cloud Project ID hosting Firestore Native Database
    PROJECT_ID: 'cloud-study-jams-3f931',
    // In local development, use local Python server
    ENDPOINT: isLocalHost ? 'http://127.0.0.1:8080' : ''
  };
})();
