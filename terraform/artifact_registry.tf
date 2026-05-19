locals {
  ar_repo_id    = "${var.name_prefix}-rag"
  ingest_image  = "${var.region}-docker.pkg.dev/${var.project_id}/${local.ar_repo_id}/ingest:latest"
  api_image     = "${var.region}-docker.pkg.dev/${var.project_id}/${local.ar_repo_id}/api:latest"
}

resource "google_artifact_registry_repository" "rag" {
  project       = var.project_id
  location      = var.region
  repository_id = local.ar_repo_id
  description   = "Docs Highlight RAG container images"
  format        = "DOCKER"

  labels = var.labels

  depends_on = [google_project_service.enabled]
}
