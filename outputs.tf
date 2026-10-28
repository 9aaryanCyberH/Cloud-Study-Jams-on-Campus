output "function_url" {
  description = "Live Cloud Function registration endpoint URL."
  value       = google_cloudfunctions2_function.register.service_config[0].uri
}

output "website_url" {
  description = "Live website URL on Google Cloud Storage."
  value       = "https://storage.googleapis.com/${google_storage_bucket.site.name}/index.html"
}

output "custom_domain_ip" {
  description = "Point an A record for your custom domain at this IP (empty if no custom domain)."
  value       = local.use_domain ? google_compute_global_address.lb[0].address : ""
}

output "custom_domain_url" {
  value = local.use_domain ? "https://${var.custom_domain}" : ""
}

output "sendgrid_secret_id" {
  description = "Add your SendGrid API key as a new version of this secret."
  value       = google_secret_manager_secret.sendgrid.secret_id
}
