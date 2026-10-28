###############################################################################
# CloudPort: static site (Cloud Storage) + Cloud Function + Firestore
# Bonus: Pub/Sub email trigger, Monitoring, custom domain + HTTPS (optional)
###############################################################################

terraform {
  required_version = ">= 1.5"
  required_providers {
    google  = { source = "hashicorp/google", version = ">= 5.30" }
    archive = { source = "hashicorp/archive", version = ">= 2.4" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  site_bucket = var.site_bucket_name != "" ? var.site_bucket_name : "${var.project_id}-cloudport-site"
  use_domain  = var.custom_domain != ""

  allowed_origins = join(",", concat(
    ["https://storage.googleapis.com"],
    local.use_domain ? ["https://${var.custom_domain}"] : [],
    var.extra_allowed_origins
  ))

  register_fn = "cloudport-register"
  confirm_fn  = "cloudport-send-confirmation"

  mime_types = {
    html = "text/html; charset=utf-8"
    css  = "text/css; charset=utf-8"
    js   = "application/javascript; charset=utf-8"
    svg  = "image/svg+xml"
    png  = "image/png"
    ico  = "image/x-icon"
  }
}

# ---------------------------------------------------------------------------
# APIs
# ---------------------------------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "eventarc.googleapis.com",
    "firestore.googleapis.com",
    "pubsub.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# Firestore (Native mode)
# ---------------------------------------------------------------------------
resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# Service accounts (least privilege, one per function)
# ---------------------------------------------------------------------------
resource "google_service_account" "register" {
  account_id   = "cloudport-register-sa"
  display_name = "CloudPort register function"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "confirm" {
  account_id   = "cloudport-confirm-sa"
  display_name = "CloudPort confirmation function"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "register_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.register.email}"
}

resource "google_pubsub_topic_iam_member" "register_publish" {
  topic  = google_pubsub_topic.registrations.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.register.email}"
}

# The Pub/Sub-triggered function is invoked by Eventarc using this account.
resource "google_project_iam_member" "confirm_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.confirm.email}"
}

resource "google_project_iam_member" "confirm_event_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.confirm.email}"
}

# ---------------------------------------------------------------------------
# Pub/Sub topic + Secret Manager (SendGrid key) - bonus email trigger
# ---------------------------------------------------------------------------
resource "google_pubsub_topic" "registrations" {
  name       = "registration-created"
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "sendgrid" {
  secret_id = "cloudport-sendgrid-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# The key itself is added out-of-band (see README) so it never enters Terraform state or git.
resource "google_secret_manager_secret_iam_member" "confirm_reads_key" {
  secret_id = google_secret_manager_secret.sendgrid.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.confirm.email}"
}

# ---------------------------------------------------------------------------
# Function source -> zip -> bucket
# ---------------------------------------------------------------------------
data "archive_file" "register" {
  type        = "zip"
  source_dir  = "${path.module}/backend"
  output_path = "${path.module}/build/register.zip"
  excludes    = ["__pycache__", "test_validate.py", ".env.example"]
}

data "archive_file" "confirm" {
  type        = "zip"
  source_dir  = "${path.module}/functions/send-confirmation"
  output_path = "${path.module}/build/send-confirmation.zip"
  excludes    = ["__pycache__"]
}

resource "google_storage_bucket" "function_src" {
  name                        = "${var.project_id}-cloudport-func-src"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  depends_on                  = [google_project_service.apis]
}

resource "google_storage_bucket_object" "register_src" {
  name   = "register-${data.archive_file.register.output_md5}.zip"
  bucket = google_storage_bucket.function_src.name
  source = data.archive_file.register.output_path
}

resource "google_storage_bucket_object" "confirm_src" {
  name   = "send-confirmation-${data.archive_file.confirm.output_md5}.zip"
  bucket = google_storage_bucket.function_src.name
  source = data.archive_file.confirm.output_path
}

# ---------------------------------------------------------------------------
# Cloud Function: registration endpoint (HTTP)
# ---------------------------------------------------------------------------
resource "google_cloudfunctions2_function" "register" {
  name     = local.register_fn
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "register_user"
    source {
      storage_source {
        bucket = google_storage_bucket.function_src.name
        object = google_storage_bucket_object.register_src.name
      }
    }
  }

  service_config {
    min_instance_count    = 0
    max_instance_count    = 5
    available_memory      = "256M"
    timeout_seconds       = 30
    service_account_email = google_service_account.register.email
    ingress_settings      = "ALLOW_ALL"
    environment_variables = {
      PROJECT_ID      = var.project_id
      COLLECTION      = "registrations"
      PUBSUB_TOPIC    = google_pubsub_topic.registrations.name
      ALLOWED_ORIGINS = local.allowed_origins
    }
  }

  depends_on = [
    google_firestore_database.default,
    google_project_iam_member.register_firestore,
    google_pubsub_topic_iam_member.register_publish,
  ]
}

# Public endpoint: the form is filled in by anonymous visitors.
resource "google_cloudfunctions2_function_iam_member" "register_public" {
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.register.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}

# ---------------------------------------------------------------------------
# Cloud Function: confirmation email (Pub/Sub trigger) - bonus
# ---------------------------------------------------------------------------
resource "google_cloudfunctions2_function" "confirm" {
  name     = local.confirm_fn
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "send_confirmation"
    source {
      storage_source {
        bucket = google_storage_bucket.function_src.name
        object = google_storage_bucket_object.confirm_src.name
      }
    }
  }

  service_config {
    min_instance_count    = 0
    max_instance_count    = 3
    available_memory      = "256M"
    timeout_seconds       = 60
    service_account_email = google_service_account.confirm.email
    ingress_settings      = "ALLOW_INTERNAL_ONLY"
    environment_variables = {
      PROJECT_ID     = var.project_id
      SENDGRID_SECRET = google_secret_manager_secret.sendgrid.secret_id
      FROM_EMAIL     = var.sendgrid_from_email
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = google_pubsub_topic.registrations.id
    retry_policy          = "RETRY_POLICY_DO_NOT_RETRY"
    service_account_email = google_service_account.confirm.email
  }

  depends_on = [
    google_project_iam_member.confirm_invoker,
    google_project_iam_member.confirm_event_receiver,
    google_secret_manager_secret_iam_member.confirm_reads_key,
  ]
}

# ---------------------------------------------------------------------------
# Static website: Cloud Storage bucket
# ---------------------------------------------------------------------------
resource "google_storage_bucket" "site" {
  name                        = local.site_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "site_public" {
  bucket = google_storage_bucket.site.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_storage_bucket_object" "site_files" {
  for_each      = { for f in fileset("${path.module}/frontend", "**") : f => f if f != "config.js" }
  bucket        = google_storage_bucket.site.name
  name          = each.key
  source        = "${path.module}/frontend/${each.key}"
  content_type  = lookup(local.mime_types, regex("[^.]+$", each.key), "application/octet-stream")
  cache_control = "public, max-age=300"
}

# Generated config: injects the live function URL (a public URL, not a secret).
resource "google_storage_bucket_object" "site_config" {
  bucket        = google_storage_bucket.site.name
  name          = "config.js"
  content_type  = "application/javascript; charset=utf-8"
  cache_control = "no-cache"
  content       = "window.CLOUDPORT_CONFIG = { ENDPOINT: \"${google_cloudfunctions2_function.register.service_config[0].uri}\" };\n"
}

# ---------------------------------------------------------------------------
# BONUS: custom domain + HTTPS (global HTTPS load balancer in front of the bucket)
# ---------------------------------------------------------------------------
resource "google_compute_global_address" "lb" {
  count      = local.use_domain ? 1 : 0
  name       = "cloudport-lb-ip"
  depends_on = [google_project_service.apis]
}

resource "google_compute_backend_bucket" "site" {
  count       = local.use_domain ? 1 : 0
  name        = "cloudport-backend-bucket"
  bucket_name = google_storage_bucket.site.name
  enable_cdn  = true
}

resource "google_compute_url_map" "https" {
  count           = local.use_domain ? 1 : 0
  name            = "cloudport-url-map"
  default_service = google_compute_backend_bucket.site[0].id
}

resource "google_compute_managed_ssl_certificate" "site" {
  count = local.use_domain ? 1 : 0
  name  = "cloudport-managed-cert"
  managed {
    domains = [var.custom_domain]
  }
}

resource "google_compute_target_https_proxy" "https" {
  count            = local.use_domain ? 1 : 0
  name             = "cloudport-https-proxy"
  url_map          = google_compute_url_map.https[0].id
  ssl_certificates = [google_compute_managed_ssl_certificate.site[0].id]
}

resource "google_compute_global_forwarding_rule" "https" {
  count      = local.use_domain ? 1 : 0
  name       = "cloudport-https-rule"
  ip_address = google_compute_global_address.lb[0].address
  port_range = "443"
  target     = google_compute_target_https_proxy.https[0].id
}

# HTTP -> HTTPS redirect
resource "google_compute_url_map" "redirect" {
  count = local.use_domain ? 1 : 0
  name  = "cloudport-http-redirect"
  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  count   = local.use_domain ? 1 : 0
  name    = "cloudport-http-proxy"
  url_map = google_compute_url_map.redirect[0].id
}

resource "google_compute_global_forwarding_rule" "http" {
  count      = local.use_domain ? 1 : 0
  name       = "cloudport-http-rule"
  ip_address = google_compute_global_address.lb[0].address
  port_range = "80"
  target     = google_compute_target_http_proxy.redirect[0].id
}

# ---------------------------------------------------------------------------
# BONUS: Cloud Monitoring (log-based metric, alerts, dashboard)
# ---------------------------------------------------------------------------
resource "google_monitoring_notification_channel" "email" {
  count        = var.notification_email != "" ? 1 : 0
  display_name = "CloudPort alerts"
  type         = "email"
  labels = {
    email_address = var.notification_email
  }
  depends_on = [google_project_service.apis]
}

resource "google_logging_metric" "function_errors" {
  name   = "cloudport_function_errors"
  filter = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name=("${local.register_fn}" OR "${local.confirm_fn}")
    severity>=ERROR
  EOT
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "error_logs" {
  display_name = "CloudPort: error logs in functions"
  combiner     = "OR"

  conditions {
    display_name = "Error log entries > 0 (5 min)"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.function_errors.name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
      trigger {
        count = 1
      }
    }
  }

  notification_channels = [for c in google_monitoring_notification_channel.email : c.name]
  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "http_5xx" {
  display_name = "CloudPort: registration endpoint 5xx"
  combiner     = "OR"

  conditions {
    display_name = "5xx responses > 0 (5 min)"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${local.register_fn}\" AND metric.labels.response_code_class=\"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
      trigger {
        count = 1
      }
    }
  }

  notification_channels = [for c in google_monitoring_notification_channel.email : c.name]
  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_dashboard" "main" {
  dashboard_json = jsonencode({
    displayName = "CloudPort overview"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width  = 6
          height = 4
          widget = {
            title = "Registration requests by response class"
            xyChart = {
              dataSets = [{
                plotType = "STACKED_BAR"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.\"service_name\"=\"${local.register_fn}\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["metric.label.\"response_code_class\""]
                    }
                  }
                }
              }]
            }
          }
        },
        {
          xPos   = 6
          width  = 6
          height = 4
          widget = {
            title = "Function error logs"
            xyChart = {
              dataSets = [{
                plotType = "LINE"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.function_errors.name}\" resource.type=\"cloud_run_revision\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_SUM"
                      crossSeriesReducer = "REDUCE_SUM"
                    }
                  }
                }
              }]
            }
          }
        },
        {
          yPos   = 4
          width  = 12
          height = 4
          widget = {
            title = "Registration function latency (p95)"
            xyChart = {
              dataSets = [{
                plotType = "LINE"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\" resource.label.\"service_name\"=\"${local.register_fn}\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_PERCENTILE_95"
                      crossSeriesReducer = "REDUCE_MAX"
                    }
                  }
                }
              }]
            }
          }
        }
      ]
    }
  })
  depends_on = [google_project_service.apis]
}
