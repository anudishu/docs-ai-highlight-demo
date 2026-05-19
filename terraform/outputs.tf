output "region" {
  value = var.region
}

output "documents_bucket" {
  value = google_storage_bucket.documents.name
}

output "upload_prefix" {
  value = var.upload_prefix
}

output "api_service_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "ingest_service_url" {
  value = google_cloud_run_v2_service.ingest.uri
}

output "upload_command" {
  value = "gcloud storage cp your.pdf gs://${google_storage_bucket.documents.name}/${var.upload_prefix}"
}
