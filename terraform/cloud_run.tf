locals {
  vertex_env = {
    GCP_PROJECT        = var.project_id
    GCS_BUCKET         = google_storage_bucket.documents.name
    UPLOAD_PREFIX      = var.upload_prefix
    EXTRACTIONS_PREFIX = var.extractions_prefix
    VERTEX_LOCATION    = var.region
    GEMINI_LOCATION    = var.gemini_location
    EMBEDDING_MODEL    = "text-embedding-005"
    GEMINI_MODEL       = var.gemini_model
    CHUNK_SIZE         = "1200"
    CHUNK_OVERLAP      = "150"
    TOP_K              = "6"
  }
}

resource "google_cloud_run_v2_service" "ingest" {
  name     = "${var.name_prefix}-ingest"
  location = var.region
  project  = var.project_id

  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = var.labels

  template {
    service_account = google_service_account.ingest.email
    timeout         = "900s"

    containers {
      image = local.ingest_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      dynamic "env" {
        for_each = {
          GCP_PROJECT        = local.vertex_env.GCP_PROJECT
          GCS_BUCKET         = local.vertex_env.GCS_BUCKET
          UPLOAD_PREFIX      = local.vertex_env.UPLOAD_PREFIX
          EXTRACTIONS_PREFIX = local.vertex_env.EXTRACTIONS_PREFIX
          VERTEX_LOCATION    = local.vertex_env.VERTEX_LOCATION
          EMBEDDING_MODEL    = local.vertex_env.EMBEDDING_MODEL
          CHUNK_SIZE         = local.vertex_env.CHUNK_SIZE
          CHUNK_OVERLAP      = local.vertex_env.CHUNK_OVERLAP
        }
        content {
          name  = env.key
          value = env.value
        }
      }
    }

    scaling {
      max_instance_count = 5
    }
  }

  depends_on = [null_resource.build_images]
}

resource "google_cloud_run_v2_service" "api" {
  name     = "${var.name_prefix}-api"
  location = var.region
  project  = var.project_id

  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = var.labels

  template {
    service_account = google_service_account.api.email

    containers {
      image = local.api_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      dynamic "env" {
        for_each = {
          GCP_PROJECT             = local.vertex_env.GCP_PROJECT
          GCS_BUCKET              = local.vertex_env.GCS_BUCKET
          VERTEX_LOCATION         = local.vertex_env.VERTEX_LOCATION
          EMBEDDING_MODEL         = local.vertex_env.EMBEDDING_MODEL
          GEMINI_MODEL            = local.vertex_env.GEMINI_MODEL
          TOP_K                   = local.vertex_env.TOP_K
          SERVICE_ACCOUNT_EMAIL   = google_service_account.api.email
        }
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.gemini_api_key != "" ? [1] : []
        content {
          name = "GEMINI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.gemini_api_key[0].secret_id
              version = "latest"
            }
          }
        }
      }
    }

    scaling {
      max_instance_count = 10
    }
  }

  depends_on = [null_resource.build_images]
}

resource "google_cloud_run_v2_service_iam_member" "api_public" {
  count = var.allow_unauthenticated_api ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
