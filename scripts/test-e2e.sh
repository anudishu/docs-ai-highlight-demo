#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/terraform"

BUCKET="$(terraform output -raw documents_bucket)"
PREFIX="$(terraform output -raw upload_prefix)"
API_URL="$(terraform output -raw api_service_url)"
PDF="${1:?Usage: $0 <path-to-text-pdf>}"

OBJECT="${PREFIX}$(basename "$PDF")"
echo "Uploading to gs://${BUCKET}/${OBJECT}"
gcloud storage cp "$PDF" "gs://${BUCKET}/${OBJECT}"

echo "Waiting 90s for ingestion..."
sleep 90

curl -sS -X POST "${API_URL}/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize this document in 3 bullet points."}' | python3 -m json.tool

echo "UI: ${API_URL}"
