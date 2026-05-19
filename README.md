# Docs Highlight RAG

Text-based PDF RAG on GCP: **GCS** → auto ingest → **Firestore** vectors → **Cloud Run** chat with **highlighted PDF sources**.

All resources in **one region** (`asia-south1` Mumbai). **Deploy with Terraform only.**

---

## Architecture

```
uploads/*.pdf  →  GCS bucket  →  Eventarc  →  Cloud Run ingest
                                              →  chunk + embed (Vertex)
                                              →  Firestore vectors
User  →  Cloud Run API  →  vector search + Gemini  →  answer + viewer_url
```

| Component | Role |
|-----------|------|
| GCS `uploads/` | PDF uploads |
| GCS `extractions/` | Ingest JSON artifacts |
| Cloud Run **ingest** | GCS trigger → PyMuPDF → Vertex embeddings → Firestore |
| Cloud Run **api** | Chat UI, `/chat`, `/view` (PDF.js highlights) |
| Firestore | Chunks + vector index |
| Vertex AI | `text-embedding-005` + Gemini (no API key; service account) |

---

## Prerequisites

- Terraform >= 1.5, `gcloud` CLI
- Project `ai-demo-495703` (or update `terraform/terraform.tfvars`)
- `gcloud auth application-default login`

---

## Deploy (Terraform only)

```bash
cd Docs-highligh-demo/terraform
terraform init
terraform apply
```

Or:

```bash
./scripts/deploy.sh
```

First apply takes **~15–25 minutes** (Cloud Build images + Firestore vector index).

---

## Upload a PDF

```bash
gcloud storage cp ./your.pdf gs://$(terraform -chdir=terraform output -raw documents_bucket)/uploads/
```

---

## Use the app

```bash
terraform -chdir=terraform output api_service_url
```

Open that URL, ask a question, click **Open highlighted PDF** on any source.

---

## Destroy

```bash
cd terraform
terraform destroy
```

Bucket uses `force_destroy = true` so objects are removed automatically.

---

## Project layout

```
terraform/     # All infrastructure + Cloud Build + Cloud Run
services/      # ingest, api, shared Python code
scripts/       # deploy.sh (terraform apply wrapper), test-e2e.sh
```
