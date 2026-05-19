#!/usr/bin/env bash
# Terraform-only deploy. All infra + image build + Cloud Run are in terraform/.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/terraform"
terraform init -input=false
terraform apply -auto-approve "$@"
terraform output
