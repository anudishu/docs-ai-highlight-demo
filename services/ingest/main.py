from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from google.cloud import storage

from shared.chunking import chunk_document
from shared.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EXTRACTIONS_PREFIX,
    GCS_BUCKET,
    GCP_PROJECT,
    UPLOAD_PREFIX,
)
from shared.embeddings import embed_texts
from shared.firestore_store import FirestoreStore, document_id_for_object
from shared.pdf_extract import extract_text_from_pdf_bytes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="docs-highlight-ingest")
store = FirestoreStore()
storage_client = storage.Client(project=GCP_PROJECT or None)


def _should_process(name: str) -> str | None:
    """Return skip reason, or None if this object should be ingested."""
    if name.endswith("/"):
        return "folder placeholder"
    if not name.lower().endswith(".pdf"):
        return "not a pdf"
    if name.startswith(EXTRACTIONS_PREFIX):
        return "extractions artifact"
    if not name.startswith(UPLOAD_PREFIX):
        return f"object must be under {UPLOAD_PREFIX}"
    return None


def process_pdf(bucket: str, name: str) -> dict:
    skip = _should_process(name)
    if skip:
        return {"skipped": True, "reason": skip}

    gcs_uri = f"gs://{bucket}/{name}"
    document_id = document_id_for_object(bucket, name)
    store.set_document_processing(
        document_id,
        gcs_uri=gcs_uri,
        bucket=bucket,
        object_name=name,
    )

    blob = storage_client.bucket(bucket).blob(name)
    pdf_bytes = blob.download_as_bytes()
    extracted = extract_text_from_pdf_bytes(pdf_bytes)
    if not extracted.full_text.strip():
        store.set_document_failed(document_id, "No extractable text in PDF")
        return {"document_id": document_id, "status": "failed", "reason": "empty text"}

    chunks = chunk_document(extracted, CHUNK_SIZE, CHUNK_OVERLAP)
    if not chunks:
        store.set_document_failed(document_id, "Chunking produced no chunks")
        return {"document_id": document_id, "status": "failed", "reason": "no chunks"}

    vectors = embed_texts([c.text for c in chunks])
    store.delete_chunks_for_document(document_id)

    chunk_rows = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk_rows.append(
            {
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "embedding": vector,
            }
        )

    store.write_chunks(
        document_id,
        gcs_uri=gcs_uri,
        bucket=bucket,
        object_name=name,
        chunks=chunk_rows,
    )

    artifact_payload = {
        "document_id": document_id,
        "gcs_uri": gcs_uri,
        "page_count": extracted.page_count,
        "chunk_count": len(chunk_rows),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "chunks": [
            {
                "chunk_index": row["chunk_index"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "text_preview": row["text"][:500],
            }
            for row in chunk_rows
        ],
    }
    if GCS_BUCKET:
        artifact_name = f"{EXTRACTIONS_PREFIX}{document_id}.json"
        storage_client.bucket(GCS_BUCKET).blob(artifact_name).upload_from_string(
            json.dumps(artifact_payload, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )

    store.set_document_ready(
        document_id,
        page_count=extracted.page_count,
        chunk_count=len(chunk_rows),
    )
    return {
        "document_id": document_id,
        "status": "ready",
        "chunk_count": len(chunk_rows),
        "gcs_uri": gcs_uri,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/events/ingest")
async def ingest_event(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        body = {}

    bucket = body.get("bucket")
    name = body.get("name")
    if not bucket or not name:
        logger.warning("Missing bucket/name in event payload: %s", body)
        return Response(status_code=400, content="bucket and name required")

    logger.info("Ingest event bucket=%s name=%s", bucket, name)
    try:
        result = process_pdf(bucket, name)
        return Response(
            status_code=200,
            content=json.dumps(result),
            media_type="application/json",
        )
    except Exception as exc:
        logger.exception("Ingest failed for gs://%s/%s", bucket, name)
        document_id = document_id_for_object(bucket, name)
        store.set_document_failed(document_id, str(exc))
        return Response(status_code=500, content=str(exc))


@app.post("/ingest")
async def manual_ingest(request: Request) -> dict:
    body = await request.json()
    bucket = body["bucket"]
    name = body["name"]
    return process_pdf(bucket, name)
