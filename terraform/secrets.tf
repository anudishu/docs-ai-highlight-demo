resource "google_secret_manager_secret" "gemini_api_key" {
  count = var.gemini_api_key != "" ? 1 : 0

  project   = var.project_id
  secret_id = "${var.name_prefix}-gemini-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "gemini_api_key" {
  count = var.gemini_api_key != "" ? 1 : 0

  secret      = google_secret_manager_secret.gemini_api_key[0].id
  secret_data = var.gemini_api_key
}

resource "google_secret_manager_secret_iam_member" "api_gemini_key" {
  count = var.gemini_api_key != "" ? 1 : 0

  project   = var.project_id
  secret_id = google_secret_manager_secret.gemini_api_key[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}
