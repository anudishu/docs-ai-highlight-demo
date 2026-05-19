locals {
  cloudbuild_sa_email      = "${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
  compute_default_sa_email = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  cloudbuild_bucket_name   = "${var.project_id}_cloudbuild"
}

resource "google_project_iam_member" "cloudbuild_logs_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${local.cloudbuild_sa_email}"
}

resource "google_storage_bucket_iam_member" "cloudbuild_sa_source" {
  bucket = local.cloudbuild_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.cloudbuild_sa_email}"
}

resource "google_project_iam_member" "compute_default_cloudbuild_builder" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.builder"
  member  = "serviceAccount:${local.compute_default_sa_email}"
}

resource "google_storage_bucket_iam_member" "compute_default_cloudbuild_source" {
  bucket = local.cloudbuild_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.compute_default_sa_email}"
}
