import os

GCP_PROJECT = os.environ.get("GCP_PROJECT", "")
SERVICE_ACCOUNT_EMAIL = os.environ.get("SERVICE_ACCOUNT_EMAIL", "").strip()
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "asia-south1")
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "us-central1")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-005")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
UPLOAD_PREFIX = os.environ.get("UPLOAD_PREFIX", "uploads/")
EXTRACTIONS_PREFIX = os.environ.get("EXTRACTIONS_PREFIX", "extractions/")

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "150"))
TOP_K = int(os.environ.get("TOP_K", "6"))


def normalize_prefix(prefix: str) -> str:
    return prefix if prefix.endswith("/") else f"{prefix}/"


UPLOAD_PREFIX = normalize_prefix(UPLOAD_PREFIX)
EXTRACTIONS_PREFIX = normalize_prefix(EXTRACTIONS_PREFIX)
