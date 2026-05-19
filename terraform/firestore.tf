resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  deletion_policy = "DELETE"

  depends_on = [google_project_service.enabled]
}

resource "google_firestore_index" "chunks_vector" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "chunks"

  fields {
    field_path = "embedding"
    vector_config {
      dimension = var.embedding_dimension
      flat {}
    }
  }

  query_scope = "COLLECTION"

  depends_on = [google_firestore_database.default]
}
