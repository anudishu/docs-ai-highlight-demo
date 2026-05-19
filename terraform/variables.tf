# User values: copy terraform.tfvars.example → terraform.tfvars (and secrets.auto.tfvars).

variable "project_id" {
  type        = string
  description = ">>> CHANGE: Your GCP project ID (set in terraform.tfvars)."
}

variable "region" {
  type        = string
  description = ">>> CHANGE (optional): Single region for all resources (default Mumbai: asia-south1)."
  default     = "asia-south1"
}

variable "name_prefix" {
  type        = string
  default     = "docs-highlight"
}

variable "labels" {
  type = map(string)
  default = {
    app = "docs-highlight-rag"
  }
}

variable "manage_project_services" {
  type    = bool
  default = true
}

variable "gemini_location" {
  type        = string
  description = "Vertex AI location for Gemini (use global when model is not in var.region)."
  default     = "us-central1"
}

variable "gemini_model" {
  type        = string
  description = "Gemini model ID (Google AI API or Vertex AI)."
  default     = "gemini-2.5-flash-lite"
}

variable "gemini_api_key" {
  type        = string
  description = ">>> CHANGE: Google AI Studio API key (secrets.auto.tfvars). Leave empty for Vertex-only Gemini."
  default     = ""
  sensitive   = true
}

variable "embedding_dimension" {
  type    = number
  default = 768
}

variable "allow_unauthenticated_api" {
  type    = bool
  default = true
}

variable "upload_prefix" {
  type    = string
  default = "uploads/"
}

variable "extractions_prefix" {
  type    = string
  default = "extractions/"
}
