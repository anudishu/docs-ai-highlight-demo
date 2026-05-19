variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "Single region for all resources (Mumbai: asia-south1)."
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
  description = "Google AI Studio API key for Gemini chat (stored in Secret Manager). Set via secrets.auto.tfvars."
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
