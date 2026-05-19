locals {
  documents_bucket_name = "${var.project_id}-docs-highlight"
}

resource "google_storage_bucket" "documents" {
  name                        = local.documents_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  labels = var.labels

  depends_on = [google_project_service.enabled]
}
