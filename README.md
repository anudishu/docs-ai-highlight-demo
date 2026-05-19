# Docs Highlight RAG

Text-based PDF RAG on GCP: **GCS** → auto ingest → **Firestore** vectors → **Cloud Run** chat with **highlighted PDF sources**.

All resources deploy to **one GCP region** (default: `asia-south1` Mumbai). Infrastructure is managed **only with Terraform**—no manual console setup required after configuration.

**Repository:** https://github.com/anudishu/docs-ai-highlight-demo

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
| GCS `uploads/` | PDF uploads (triggers ingest) |
| GCS `extractions/` | Ingest JSON artifacts |
| Cloud Run **ingest** | GCS trigger → PyMuPDF → Vertex embeddings → Firestore |
| Cloud Run **api** | Chat UI, `/chat`, `/view` (PDF.js highlights) |
| Firestore | Chunks + vector index |
| Vertex AI | `text-embedding-005` (always via service account) |
| Gemini | Google AI Studio API key **or** Vertex AI (see configuration) |

---

## What you need before starting

| Requirement | Notes |
|-------------|--------|
| **GCP project** | With billing enabled |
| **Permissions** | `Owner` or roles that can enable APIs, create IAM, Cloud Run, Firestore, GCS, Secret Manager |
| **Terraform** | `>= 1.5.0` — [install](https://developer.hashicorp.com/terraform/install) |
| **gcloud CLI** | [install](https://cloud.google.com/sdk/docs/install) |
| **Google AI Studio key** (recommended) | For Gemini chat — [create key](https://aistudio.google.com/apikey) |

Estimated first deploy time: **15–25 minutes** (Cloud Build images + Firestore vector index).

---

## Step-by-step deployment

### Step 1 — Clone the repository

```bash
git clone https://github.com/anudishu/docs-ai-highlight-demo.git
cd docs-ai-highlight-demo
```

### Step 2 — Authenticate with Google Cloud

```bash
# Log in and set Application Default Credentials (used by Terraform)
gcloud auth login
gcloud auth application-default login

# >>> CHANGE: replace with your GCP project ID
export PROJECT_ID="your-gcp-project-id"

gcloud config set project "$PROJECT_ID"
```

### Step 3 — Create Terraform variable files

Terraform reads **two local files** (both are gitignored—never commit them):

#### 3a. `terraform/terraform.tfvars` (required)

Copy the example and edit every value marked `CHANGE`:

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Open `terraform/terraform.tfvars` and set at minimum:

| Variable | Required? | What to set |
|----------|-----------|-------------|
| `project_id` | **Yes** | Your GCP project ID |
| `region` | Optional | GCP region for all resources (default `asia-south1`) |
| `name_prefix` | Optional | Prefix for Cloud Run services, SAs, secrets (default `docs-highlight`) |
| `gemini_model` | Optional | Gemini model ID (default `gemini-2.5-flash-lite`) |
| `allow_unauthenticated_api` | Optional | `true` = public chat UI; `false` = IAM-only |

#### 3b. `terraform/secrets.auto.tfvars` (required for chat)

Gemini chat needs an API key unless you rely on Vertex-only mode (see [Gemini options](#gemini-options)).

```bash
cat > terraform/secrets.auto.tfvars <<'EOF'
# >>> CHANGE: paste your Google AI Studio API key
gemini_api_key = "your-google-ai-studio-api-key"
EOF
```

> **Security:** `secrets.auto.tfvars` and `terraform.tfvars` are in `.gitignore`. Do not commit API keys or project-specific secrets.

### Step 4 — (Optional) Pre-enable GCP APIs

Terraform can enable APIs automatically (`manage_project_services = true` in `terraform.tfvars`). To enable them yourself first:

```bash
./scripts/enable-apis.sh "$PROJECT_ID"
```

### Step 5 — Initialize Terraform

```bash
cd terraform
terraform init
```

Review the plan (recommended on first run):

```bash
terraform plan
```

### Step 6 — Deploy infrastructure

From the repo root:

```bash
./scripts/deploy.sh
```

Or manually from `terraform/`:

```bash
cd terraform
terraform apply
```

Type `yes` when prompted. This creates:

- GCS bucket, Firestore DB + vector index
- Artifact Registry + Cloud Build (Docker images for `ingest` and `api`)
- Cloud Run services, Eventarc trigger, IAM, Secret Manager (if API key set)

When finished, note the outputs:

```bash
terraform output
```

### Step 7 — Upload a PDF

Use a **text-based** PDF (not a scanned image-only PDF).

```bash
# From repo root, after deploy
gcloud storage cp ./your-document.pdf \
  "gs://$(terraform -chdir=terraform output -raw documents_bucket)/$(terraform -chdir=terraform output -raw upload_prefix)"
```

Or use the helper command from Terraform output:

```bash
terraform -chdir=terraform output -raw upload_command
# Then replace your.pdf with your file path
```

Ingestion runs automatically when the file lands in `uploads/`. Wait **~1–2 minutes** for chunking and embedding.

### Step 8 — Open the app and test

```bash
terraform -chdir=terraform output api_service_url
```

1. Open the URL in a browser.
2. Ask a question about your uploaded PDF.
3. Click **Open highlighted PDF** on any source citation.

**CLI smoke test** (optional):

```bash
./scripts/test-e2e.sh ./your-document.pdf
```

---

## Configuration reference (what to change)

All user-specific values live in **`terraform/terraform.tfvars`** and **`terraform/secrets.auto.tfvars`**. No project IDs are hardcoded in `.tf` files—they use `var.project_id`.

### `terraform/terraform.tfvars`

| Variable | Default | Change when… |
|----------|---------|--------------|
| `project_id` | *(none)* | **Always** — set your GCP project |
| `region` | `asia-south1` | You want a different region (must support Vertex AI + Cloud Run) |
| `name_prefix` | `docs-highlight` | Avoid naming clashes in a shared project |
| `manage_project_services` | `true` | You pre-enabled APIs and want Terraform to skip API enablement |
| `gemini_model` | `gemini-2.5-flash-lite` | You want a different Gemini model |
| `allow_unauthenticated_api` | `true` | You need the API private (requires authenticated `curl`/browser) |

### `terraform/secrets.auto.tfvars`

| Variable | Default | Change when… |
|----------|---------|--------------|
| `gemini_api_key` | `""` | **Recommended** — set for Google AI Studio Gemini chat |

### Advanced variables (`terraform/variables.tf`)

Edit defaults in `terraform.tfvars` only if you need them:

| Variable | Default | Purpose |
|----------|---------|---------|
| `gemini_location` | `us-central1` | Vertex AI region for Gemini when **not** using API key |
| `embedding_dimension` | `768` | Must match `text-embedding-005` |
| `upload_prefix` | `uploads/` | GCS folder for incoming PDFs |
| `extractions_prefix` | `extractions/` | GCS folder for ingest JSON |
| `labels` | `app = docs-highlight-rag` | Resource labels |

### Resources named from your config

These are **derived** from `project_id` / `name_prefix`—you do not edit them in code:

| Resource | Naming pattern |
|----------|----------------|
| GCS bucket | `{project_id}-docs-highlight` |
| Cloud Run ingest | `{name_prefix}-ingest` |
| Cloud Run API | `{name_prefix}-api` |
| Secret (if key set) | `{name_prefix}-gemini-api-key` |

### Gemini options

| Mode | Configure | Chat uses |
|------|-----------|-----------|
| **Google AI Studio** (default) | Set `gemini_api_key` in `secrets.auto.tfvars` | API key via Secret Manager |
| **Vertex AI only** | Leave `gemini_api_key` empty | Service account + `gemini_location` |

Embeddings **always** use Vertex AI (`text-embedding-005`) in `var.region` via the ingest/API service accounts.

---

## Troubleshooting

| Issue | Check |
|-------|--------|
| `terraform apply` permission errors | Caller has Owner or sufficient IAM on the project |
| APIs not enabled | Run `./scripts/enable-apis.sh "$PROJECT_ID"` or set `manage_project_services = true` |
| Chat returns errors | `gemini_api_key` set in `secrets.auto.tfvars` and apply re-run; or use Vertex-only |
| No search results | PDF is text-based; wait after upload; confirm object under `uploads/` |
| Ingest not running | Cloud Run ingest logs; Eventarc trigger on bucket |
| Build fails | Cloud Build API enabled; billing active |

View logs:

```bash
gcloud run services logs read docs-highlight-ingest --region=asia-south1 --limit=50
gcloud run services logs read docs-highlight-api --region=asia-south1 --limit=50
```

>>> **CHANGE:** Replace `asia-south1` and `docs-highlight-*` if you changed `region` or `name_prefix`.

---

## Tear down

```bash
cd terraform
terraform destroy
```

The documents bucket uses `force_destroy = true`, so GCS objects are deleted with the stack.

---

## Project layout

```
terraform/
  terraform.tfvars.example   # Template — copy to terraform.tfvars
  variables.tf               # All configurable inputs (defaults documented)
  *.tf                       # Infrastructure (uses var.project_id everywhere)
services/
  ingest/                    # GCS-triggered PDF ingest
  api/                       # Chat + PDF highlight viewer
  shared/                    # Chunking, embeddings, Firestore
scripts/
  deploy.sh                  # terraform init + apply
  enable-apis.sh             # Optional manual API enablement
  test-e2e.sh                # Upload PDF + curl /chat
```

---

## Files you must not commit

| File | Contains |
|------|----------|
| `terraform/terraform.tfvars` | Your `project_id` and settings |
| `terraform/secrets.auto.tfvars` | Gemini API key |
| `terraform/*.tfstate*` | Infrastructure state |
| `terraform/.terraform/` | Provider cache |
| `.env` | Local secrets |

Use only `terraform/terraform.tfvars.example` as the template in git.
