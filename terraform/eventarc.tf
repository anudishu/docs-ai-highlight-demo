data "google_storage_project_service_account" "gcs" {
  project = var.project_id
}

resource "google_project_iam_member" "gcs_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs.email_address}"
}

resource "google_eventarc_trigger" "gcs_finalize" {
  name     = "${var.name_prefix}-gcs-finalize"
  location = var.region
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }

  matching_criteria {
    attribute = "bucket"
    value     = google_storage_bucket.documents.name
  }

  # Prefix filtering is enforced in the ingest service (skips extractions/, non-PDF).

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.ingest.name
      region  = var.region
      path    = "/events/ingest"
    }
  }

  service_account = google_service_account.eventarc.email

  depends_on = [
    google_project_service.enabled,
    google_project_iam_member.gcs_pubsub_publisher,
    google_cloud_run_v2_service.ingest,
    google_cloud_run_v2_service_iam_member.eventarc_invokes_ingest,
  ]
}
