data "archive_file" "services" {
  type        = "zip"
  source_dir  = "${path.module}/../services"
  output_path = "${path.module}/.build/services-source.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache"]
}

# Cloud Build runs as part of `terraform apply` (no separate deploy script).
resource "null_resource" "build_images" {
  triggers = {
    source_md5 = data.archive_file.services.output_md5
    region     = var.region
    repo       = local.ar_repo_id
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -euo pipefail
      gcloud builds submit "${path.module}/../services" \
        --project="${var.project_id}" \
        --region="${var.region}" \
        --config="${path.module}/../services/cloudbuild.yaml" \
        --substitutions="_REGION=${var.region},_REPO=${local.ar_repo_id}"
    EOT
  }

  depends_on = [
    google_artifact_registry_repository.rag,
    google_project_iam_member.cloudbuild_ar_writer,
    google_storage_bucket_iam_member.cloudbuild_sa_source,
    google_project_iam_member.compute_default_cloudbuild_builder,
    google_storage_bucket_iam_member.compute_default_cloudbuild_source,
  ]
}
