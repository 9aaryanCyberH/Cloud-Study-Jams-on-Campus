variable "project_id" {
  description = "GCP project ID to deploy into."
  type        = string
}

variable "region" {
  description = "Region for Cloud Functions, the buckets and Pub/Sub triggers."
  type        = string
  default     = "asia-south1"
}

variable "firestore_location" {
  description = "Firestore database location (cannot be changed later)."
  type        = string
  default     = "asia-south1"
}

variable "site_bucket_name" {
  description = "Globally unique name for the static-site bucket. Empty = <project_id>-cloudport-site."
  type        = string
  default     = ""
}

variable "extra_allowed_origins" {
  description = "Extra origins allowed by the function's CORS check (e.g. local dev)."
  type        = list(string)
  default     = ["http://localhost:8080"]
}

variable "custom_domain" {
  description = "BONUS: custom domain (e.g. cloudport.example.com). Empty = skip the HTTPS load balancer."
  type        = string
  default     = ""
}

variable "notification_email" {
  description = "BONUS: email address that receives Cloud Monitoring alerts. Empty = alerts are created without notifications."
  type        = string
  default     = ""
}

variable "sendgrid_from_email" {
  description = "BONUS: verified SendGrid sender address for confirmation emails. Empty = email step is skipped."
  type        = string
  default     = ""
}
